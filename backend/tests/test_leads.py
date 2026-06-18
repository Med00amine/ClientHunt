import csv
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models import BusinessContact, Company, ExportRecord, Opportunity, Suppression, utcnow
from app.services import exporter, leads, research, runner
from app.services.safefetch import SafeFetcher
from .helpers import FakeAdapter, factory_for, raw
from .test_csv_and_runs import go, read

APPLY = "We need a Python/FastAPI/LLM engineer on AWS. To apply, email your resume to jobs@acme.example. " * 2


def kinds(db, run):
    return {e.kind: e for e in db.scalars(select(ExportRecord).where(ExportRecord.run_id == run.id))}


# ---------------------------------------------------------------- extraction and classification
def test_extract_ignores_noise_and_never_guesses():
    t = ("Email me at dev@corp.example or noreply@corp.example. Logo: sprite@2x.png. Obfuscated: jobs [at] corp [dot] example. "
         "Also Jane.Doe+hn@Corp.Example.")
    got = {e["email"] for e in leads.extract_emails(t)}
    assert got == {"dev@corp.example", "Jane.Doe+hn@Corp.Example"}


def test_invitation_detection_and_classification():
    inv = leads.extract_emails("To apply send your CV to hr@acme.example")[0]
    plain = leads.extract_emails("Our founder is a@acme.example")[0]
    assert inv["invited"] and not plain["invited"]
    assert leads.classify("hr@acme.example", True, "listing")[:2] == ("application_invited", "eligible")
    assert leads.classify("x@gmail.com", True, "listing")[1] == "review_required"     # free-mail = an individual
    assert leads.classify("a@acme.example", False, "listing")[1] == "review_required"
    assert leads.classify("careers@acme.example", False, "website")[1] == "eligible"
    assert leads.classify("info@acme.example", False, "website")[1] == "review_required"


def test_mailto_links_are_kept_by_html_to_text():
    from app.textutil import html_to_text
    assert "jobs@acme.example" in html_to_text('<p>Apply: <a href="mailto:jobs@acme.example">our team</a></p>')


# ---------------------------------------------------------------- pipeline + exports
def test_listing_email_is_stored_with_provenance_and_exported(db):
    run = go(db, {"fake": FakeAdapter([raw(1, description=APPLY, company_name="Acme")])})
    c = db.scalar(select(BusinessContact))
    o = db.scalar(select(Opportunity))
    assert c.email == "jobs@acme.example" and c.source_url == o.original_url and c.retrieved_at is not None
    assert c.source_type == "hiring_post" and c.verified_status == "unverified"       # never "verified" by syntax
    assert c.outreach_eligibility == "eligible" and "apply" in c.eligibility_basis.lower()
    assert o.apply_method == "email" and any("email to apply" in x for x in o.ease_signals)
    ex = kinds(db, run)
    assert set(ex) == {"opportunities", "emails"} and ex["emails"].row_count == 1
    rows = read(ex["emails"].path)
    assert rows[0]["business_email"] == "jobs@acme.example" and rows[0]["listing_url"] == o.original_url
    assert rows[0]["email_source_url"] == o.original_url and rows[0]["outreach_eligibility"] == "eligible"
    opp_row = read(ex["opportunities"].path)[0]
    assert opp_row["business_email"] == "jobs@acme.example" and opp_row["outreach_eligibility"] == "eligible"
    assert float(opp_row["hiring_ease_score"]) == o.ease_score and opp_row["apply_method"] == "email"


def test_run_without_emails_still_creates_header_only_emails_csv(db):
    run = go(db, {"fake": FakeAdapter([raw(1)])})
    e = kinds(db, run)["emails"]
    assert e.row_count == 0
    assert open(e.path, encoding="utf-8-sig").read().strip() == ",".join(exporter.EMAIL_COLUMNS)


def test_require_email_filter(db):
    run = go(db, {"fake": FakeAdapter([raw(1, description=APPLY), raw(2)])}, require_email=True)
    assert run.stored == 1 and run.rejected_irrelevant == 1


def test_min_ease_filter(db):
    easy = raw(1, description=APPLY + " Starting ASAP, contract role.")
    hard = raw(2, description="Senior role. No contractors. Must be located in the US. Python FastAPI AWS LLM. " * 4,
               location_requirements="US only", engagement_type="full_time")
    run = go(db, {"fake": FakeAdapter([easy, hard])}, min_ease=40)
    assert run.stored == 1 and db.scalar(select(Opportunity)).external_id == "1"


def test_suppressed_email_never_exported_and_not_eligible(db):
    db.add(Suppression(domain="acme.example", reason="opt-out")); db.commit()
    run = go(db, {"fake": FakeAdapter([raw(1, description=APPLY)])})
    c = db.scalar(select(BusinessContact))
    assert c.suppressed and c.outreach_eligibility == "not_eligible"
    assert kinds(db, run)["emails"].row_count == 0
    assert read(kinds(db, run)["opportunities"].path)[0]["business_email"] == ""


def test_email_csv_is_formula_safe(db):
    d = "=cmd|calc to apply email your CV to jobs@acme.example python fastapi llm aws " * 3
    run = go(db, {"fake": FakeAdapter([raw(1, description=d, title="+SUM(1)")])})
    row = read(kinds(db, run)["emails"].path)[0]
    assert row["email_context"].startswith("'=") or not row["email_context"].startswith("=")
    assert row["listing_title"].startswith("'+")


def test_existing_contact_without_provenance_gains_it(db):
    db.add(BusinessContact(email="jobs@acme.example", email_norm="jobs@acme.example", domain="acme.example")); db.commit()
    go(db, {"fake": FakeAdapter([raw(1, description=APPLY)])})
    c = db.scalar(select(BusinessContact))
    assert db.query(BusinessContact).count() == 1 and c.source_url and c.opportunity_id


def test_not_eligible_contact_stays_not_eligible(db):
    db.add(BusinessContact(email="jobs@acme.example", email_norm="jobs@acme.example", domain="acme.example",
                           outreach_eligibility="not_eligible")); db.commit()
    run = go(db, {"fake": FakeAdapter([raw(1, description=APPLY)])})
    assert db.scalar(select(BusinessContact)).outreach_eligibility == "not_eligible"
    assert kinds(db, run)["emails"].row_count == 0


# ---------------------------------------------------------------- ease heuristic
def test_ease_signals_positive_and_negative():
    now = utcnow()
    good, sig, m = leads.compute_ease("Contract Python dev", "Startup, ASAP start, hiring several engineers", "contract",
                                      "worldwide", now - timedelta(days=1), True, now)
    assert good >= 80 and m == "email" and any("urgent" in x.lower() or "soon" in x.lower() for x in sig)
    bad, sig2, m2 = leads.compute_ease("Engineer", "No contractors or agencies. Must be located in the US.", "unknown",
                                       "restricted", now - timedelta(days=60), False, now)
    assert bad == 0 and m2 == "link" and any("no contractors" in x.lower() for x in sig2)
    assert 0 <= good <= 100


# ---------------------------------------------------------------- company website discovery
SITE = {
    "/": "<html><head><title>Acme</title></head><body><p>We build robots with Python.</p></body></html>",
    "/contact": '<html><body><a href="mailto:careers@acme.example">Careers</a> <a href="mailto:info@acme.example">General</a> '
                'john.smith@acme.example press@acme.example hello@othersite.example</body></html>',
}


def site_fetcher():
    def h(r):
        if r.url.path == "/robots.txt":
            return httpx.Response(404)
        body = SITE.get(r.url.path)
        return httpx.Response(200, text=body, headers={"content-type": "text/html"}) if body else httpx.Response(404)
    return SafeFetcher(httpx.Client(transport=httpx.MockTransport(h)), resolver=lambda host: ["93.184.216.34"])


def test_website_discovery_role_mailboxes_same_domain_only(db):
    run = go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    research.research_company(db, db.get(Company, o.company_id), o, site_fetcher())
    emails = {c.email: c for c in db.scalars(select(BusinessContact))}
    assert set(emails) == {"careers@acme.example", "info@acme.example"}      # no person, no other domain, no press@
    assert emails["careers@acme.example"].outreach_eligibility == "eligible"
    assert emails["info@acme.example"].outreach_eligibility == "review_required"
    for c in emails.values():
        assert c.source_url == "https://acme.example/contact" and c.source_type == "company_website" and c.retrieved_at


def test_site_domain_helper():
    assert research.site_domain("https://www.acme.example/x") == "acme.example"
    assert research.site_domain("https://jobs.acme.co.uk") == "acme.co.uk"


# ---------------------------------------------------------------- API
def test_leads_endpoint_filters_and_emails_download(client, db):
    imported = BusinessContact(email="old@legacy.example", email_norm="old@legacy.example", domain="legacy.example")
    db.add(imported); db.commit()                                              # no provenance: never listed/exported
    items = [raw(1, description=APPLY, company_name="Acme"),
             raw(2, description=APPLY.replace("jobs@", "us@"), company_name="UsCo", location_requirements="US only"),
             raw(3, company_name="NoMail")]
    body = {"search": {"name": "t", "min_fit": 0, "remote_only": False, "posted_within_days": None, "sources": ["fake"],
                       "max_companies": 0, "max_drafts": 0}}
    rid = client.post("/api/runs", json=body).json()["id"]
    runner.execute_run(db, rid, factory_for({"fake": FakeAdapter(items)}))
    d = client.get("/api/leads").json()
    assert [i["company_name"] for i in d["items"]] == ["Acme"]                 # US-only hidden, no-email hidden
    assert d["emails"] == ["jobs@acme.example"]
    assert d["items"][0]["contacts"][0]["source_url"] and d["items"][0]["ease_score"] > 0
    both = client.get("/api/leads?hide_restricted=false").json()
    assert {i["company_name"] for i in both["items"]} == {"Acme", "UsCo"}
    assert len(client.get("/api/leads?has_email=false&hide_restricted=false").json()["items"]) == 3
    ex = client.post("/api/exports/emails").json()
    assert ex["status"] == "ok" and ex["row_count"] == 2
    r = client.get(ex["download_url"])
    text = r.content.decode("utf-8-sig")
    assert "jobs@acme.example" in text and "old@legacy.example" not in text
    run = client.get(f"/api/runs/{rid}").json()
    assert run["emails_found"] == 2 and {e["kind"] for e in run["exports"]} == {"opportunities", "emails"}
    ov = client.get("/api/overview").json()
    assert ov["emails_found"] == 2 and ov["apply_by_email_leads"] == 2


def test_migration_0003_upgrades_existing_rows(tmp_path):
    import sqlite3
    from alembic import command
    from alembic.config import Config
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(root / "alembic.ini")); cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()
    command.upgrade(cfg, "0002")
    con = sqlite3.connect(tmp_path / "m.db")
    con.execute("insert into business_contacts (email,email_norm,domain,name,role,company_name,is_generic,source_type,source_url,source_note,verified_status,outreach_eligibility,eligibility_basis,suppressed,created_at) values ('a@b.com','a@b.com','b.com','','','',0,'x','','','unverified','unknown','',0,'2026-01-01')")
    con.commit(); con.close()
    command.upgrade(cfg, "head")
    con = sqlite3.connect(tmp_path / "m.db")
    assert con.execute("select contact_purpose, opportunity_id from business_contacts").fetchone() == ("", None)
    command.downgrade(cfg, "0002")


def test_non_engineering_titles_are_capped():
    from app.scoring import score
    bd = score(raw(1, title="Irash Tech | Business Development Manager (Freelance, Commission-only)",
                   description="Python FastAPI AWS LLM RAG Docker " * 20), None, [])
    eng = score(raw(2, title="Acme | Growth Marketing Engineer (AI-First)", description="Python FastAPI AWS LLM RAG Docker " * 20), None, [])
    assert bd["total"] <= 30 and "non-engineering" in bd["explanation"]
    assert eng["total"] > 30


def test_hn_key_value_post_gets_company_from_company_line(db):
    import json as _json
    from app.adapters import hn_hiring
    def h(req):
        if "author_whoishiring" in str(req.url):
            return httpx.Response(200, json={"hits": [{"objectID": "100", "title": "Ask HN: Who is hiring? (October 2026)"}]})
        return httpx.Response(200, json={"hits": [{"objectID": "7", "parent_id": 100, "comment_text":
            "Location: Dubrovnik, Croatia (CET)<p>Company: Quantum Minds<p>To apply email jobs@quantumminds.example Python"}]})
    a = hn_hiring.HNHiring(db, httpx.Client(transport=httpx.MockTransport(h)))
    from app.types import SearchParams
    out = a.fetch(SearchParams())
    assert out[0].company_name == "Quantum Minds"


def test_presets_follow_code_updates(db):
    from app.models import SearchProfile
    from app.services import presets
    row = db.scalar(select(SearchProfile).where(SearchProfile.name.like("Easy to reach%")))
    row.params = {"min_fit": 1}; db.commit()
    presets.seed(db)
    db.refresh(row)
    assert row.params["min_fit"] == 35.0 and row.params["require_email"] is True


def test_leads_default_ranking_combines_fit_and_ease(client, db):
    strong = raw(1, description=APPLY + " Contract, start ASAP.", company_name="Strong")
    weak = raw(2, title="Sales role", description="Python. To apply email x@weak.example. Contract ASAP. Startup. Multiple roles.", company_name="Weak")
    body = {"search": {"name": "t", "min_fit": 0, "remote_only": False, "posted_within_days": None, "sources": ["fake"], "max_companies": 0, "max_drafts": 0}}
    rid = client.post("/api/runs", json=body).json()["id"]
    runner.execute_run(db, rid, factory_for({"fake": FakeAdapter([weak, strong])}))
    names = [i["company_name"] for i in client.get("/api/leads?hide_restricted=false").json()["items"]]
    assert names[0] == "Strong"
