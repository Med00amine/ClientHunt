import hashlib

import pytest
from sqlalchemy import inspect, select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Opportunity
from app.services import runner
from .helpers import FakeAdapter, factory_for, raw
from .test_logic import UPWORK_EMAIL


def run_via_api(client, db, items, **search):
    body = {"search": {"name": "t", "min_fit": 0, "remote_only": False, "posted_within_days": None, "sources": ["fake"],
                       "max_companies": 0, "max_drafts": 0, **search}}
    r = client.post("/api/runs", json=body)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    rid = r.json()["id"]
    runner.execute_run(db, rid, factory_for({"fake": FakeAdapter(items)}))
    return client.get(f"/api/runs/{rid}").json()


def test_download_matches_saved_file(client, db):
    run = run_via_api(client, db, [raw(1), raw(2)])
    ex = [e for e in run["exports"] if e["kind"] == "opportunities"][0]
    r = client.get(ex["download_url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    path = get_settings().exports_dir / ex["filename"]
    assert r.content == path.read_bytes()
    assert hashlib.sha256(r.content).hexdigest() == ex["sha256"]
    assert ex["row_count"] == 2


def test_tampered_export_refused(client, db):
    run = run_via_api(client, db, [raw(1)])
    ex = [e for e in run["exports"] if e["kind"] == "opportunities"][0]
    (get_settings().exports_dir / ex["filename"]).write_text("tampered")
    assert client.get(ex["download_url"]).status_code == 409


def test_export_history_and_reexport_creates_new_file(client, db):
    run = run_via_api(client, db, [raw(1)])
    again = client.post(f"/api/runs/{run['id']}/export").json()
    hist = [e for e in client.get("/api/exports").json() if e["kind"] == "opportunities"]
    assert len(hist) == 2 and again["filename"] != [e for e in run["exports"] if e["kind"] == "opportunities"][0]["filename"]


def test_overview_reflects_database_not_samples(client, db):
    assert client.get("/api/overview").json()["opportunities_total"] == 0
    run_via_api(client, db, [raw(1), raw(2)])
    o = client.get("/api/overview").json()
    assert o["opportunities_total"] == 2 and o["new_since_previous_run"] == 2 and o["applications_submitted"] == 0


def test_presets_exist(client):
    names = {p["name"] for p in client.get("/api/profiles").json()}
    assert len(names) >= 5 and "AI/LLM and RAG projects" in names


def test_approval_gate_and_application_requires_approved_draft(client, db):
    run_via_api(client, db, [raw(1)])
    oid = client.get("/api/opportunities").json()["items"][0]["id"]
    # cannot record a submission without an approved draft
    assert client.post(f"/api/opportunities/{oid}/applications", json={}).status_code == 409
    d = client.post(f"/api/opportunities/{oid}/drafts").json()
    assert client.get(f"/api/opportunities/{oid}").json()["application_status"] == "none"  # drafting != applying
    assert client.post(f"/api/opportunities/{oid}/applications", json={}).status_code == 409
    if d["warnings"]:
        assert client.post(f"/api/drafts/{d['id']}/approve", json={}).status_code == 409
    ok = client.post(f"/api/drafts/{d['id']}/approve", json={"acknowledge_warnings": True})
    assert ok.json()["status"] == "approved"
    # editing cancels approval
    ed = client.patch(f"/api/drafts/{d['id']}", json={"body": ok.json()["body"] + " extra"}).json()
    assert ed["status"] == "draft"
    assert client.post(f"/api/opportunities/{oid}/applications", json={}).status_code == 409
    client.post(f"/api/drafts/{d['id']}/approve", json={"acknowledge_warnings": True})
    a = client.post(f"/api/opportunities/{oid}/applications", json={})
    assert a.status_code == 200 and a.json()["status"] == "submitted"
    assert client.post(f"/api/opportunities/{oid}/applications", json={}).status_code == 409
    aid = a.json()["id"]
    assert client.patch(f"/api/applications/{aid}", json={"status": "interview"}).json()["status"] == "interview"
    assert client.get("/api/overview").json()["interviews"] == 1


def test_exclusion_and_score_override(client, db):
    run_via_api(client, db, [raw(1)])
    o = client.get("/api/opportunities").json()["items"][0]
    p = client.patch(f"/api/opportunities/{o['id']}", json={"score_override": 5}).json()
    assert p["fit_score"] == 5 and p["auto_score"] == o["auto_score"]
    client.patch(f"/api/opportunities/{o['id']}", json={"review_status": "excluded", "exclusion_reason": "not a fit"})
    assert client.get("/api/opportunities").json()["total"] == 0
    assert client.get("/api/opportunities?show_excluded=true").json()["total"] == 1


def test_validation_errors(client):
    assert client.post("/api/runs", json={}).status_code == 422
    assert client.post("/api/opportunities/manual", json={"title": "x", "url": "javascript:alert(1)"}).status_code == 422
    assert client.patch("/api/opportunities/999", json={}).status_code == 404


def test_manual_and_alert_import_create_exports_and_opps(client):
    r = client.post("/api/opportunities/manual", json={"title": "Agency needs Python subcontractor", "url": "https://agency.example/careers/1",
                                                       "description": "Python FastAPI AWS contractor " * 10, "company_name": "Agency"})
    assert r.status_code == 200 and r.json()["run"]["exports"][0]["row_count"] == 1
    r2 = client.post("/api/alerts/import", json={"text": UPWORK_EMAIL})
    assert r2.json()["parsed"] == 1
    items = client.get("/api/opportunities").json()["items"]
    assert {i["source"] for i in items} >= {"manual", "alert_upwork"}
    assert any(i["url"] == "https://www.upwork.com/jobs/~0123456789" for i in items)


def test_contacts_api_flow(client, db, tmp_path):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["email", "name", "company"]); ws.append(["a@x.com", "A", "X"]); f = tmp_path / "c.xlsx"; wb.save(f)
    r = client.post("/api/contacts/import", files={"file": ("c.xlsx", f.read_bytes())})
    assert r.status_code == 200 and r.json()["imported"] == 1
    c = client.get("/api/contacts").json()
    assert c["items"][0]["outreach_eligibility"] == "unknown" and c["items"][0]["provenance_missing"]
    cid = c["items"][0]["id"]
    assert client.patch(f"/api/contacts/{cid}/eligibility", json={"value": "eligible", "basis": "x"}).status_code == 422
    # contacts CSV only includes eligible contacts with provenance -> empty here
    ex = client.post("/api/exports/contacts").json()
    assert ex["status"] == "ok" and ex["row_count"] == 0
    assert client.post("/api/contacts/import", files={"file": ("c.txt", b"x")}).status_code == 422


def test_contact_only_exported_when_eligible_with_provenance(client, db):
    r = client.post("/api/contacts", json={"email": "hello@agency.example", "source_url": "https://agency.example/contact", "company_name": "Agency"})
    cid = r.json()["id"]
    assert client.patch(f"/api/contacts/{cid}/eligibility", json={"value": "eligible", "basis": "Public B2B address; local rules reviewed"}).status_code == 200
    ex = client.post("/api/exports/contacts").json()
    assert ex["row_count"] == 1
    client.post("/api/suppressions", json={"email": "hello@agency.example", "reason": "opt-out"})
    assert client.post("/api/exports/contacts").json()["row_count"] == 0


def test_portfolio_toggle_and_rescore(client, db):
    run_via_api(client, db, [raw(1)])
    before = client.get("/api/opportunities").json()["items"][0]["auto_score"]
    client.patch("/api/portfolio/rag-project", json={"verified": True})
    client.post("/api/opportunities/rescore")
    after = client.get("/api/opportunities").json()["items"][0]["auto_score"]
    assert after >= before


def test_retry_and_cancel_endpoints(client, db):
    r = client.post("/api/runs", json={"search": {"sources": ["fake"]}}).json()
    assert client.post(f"/api/runs/{r['id']}/retry").status_code == 409
    c = client.post(f"/api/runs/{r['id']}/cancel").json()
    assert c["status"] == "cancelled"
    new = client.post(f"/api/runs/{r['id']}/retry").json()
    assert new["retry_count"] == 1 and new["status"] == "pending"


def test_auth_required_when_password_set(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "s3cret"}).status_code == 200
    assert client.get("/api/overview").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/overview").status_code == 401
    client.cookies.set("ch_session", "1.deadbeef")
    assert client.get("/api/overview").status_code == 401


def test_download_requires_auth(client, db, monkeypatch):
    run = run_via_api(client, db, [raw(1)])
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get(run["exports"][0]["download_url"]).status_code == 401


def test_migrations_create_expected_tables():
    names = set(inspect(engine).get_table_names())
    for t in ["sources", "search_profiles", "research_runs", "opportunities", "companies", "business_contacts",
              "research_evidence", "proposal_drafts", "applications", "client_conversations", "suppressions",
              "export_history", "usage_events", "alembic_version"]:
        assert t in names, t


def test_contacts_and_opportunities_are_separate_tables():
    cols = {c["name"] for c in inspect(engine).get_columns("opportunities")}
    assert "email" not in cols and "email_norm" not in cols
    assert "business_email" not in cols


def test_migration_0002_upgrades_existing_rows(tmp_path):
    """Upgrade a database created at revision 0001 that already holds a run."""
    from alembic import command
    from alembic.config import Config
    import sqlite3
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(root / "alembic.ini")); cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "0001")
    con = sqlite3.connect(tmp_path / "m.db")
    con.execute("insert into research_runs (params,status,created_at,current_source,sources_queried,source_results,discovered,stored,new_count,rejected_irrelevant,rejected_duplicate,selected_for_review,companies_researched,drafts_generated,cost_usd,estimated_cost_usd,retry_count,cancel_requested,last_error,errors,incomplete_notes,export_status,profile_name) values ('{}','completed','2026-01-01',' ','[]','{}',0,0,0,0,0,0,0,0,0,0,0,0,'','[]','[]','none','x')")
    con.commit(); con.close()
    command.upgrade(cfg, "head")
    con = sqlite3.connect(tmp_path / "m.db")
    assert con.execute("select info_notes from research_runs").fetchone()[0] == "[]"
    command.downgrade(cfg, "0001")
