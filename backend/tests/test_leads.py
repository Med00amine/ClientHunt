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
    assert len(client.get("/api/leads?has_email=false&hide_restricted=false&source=fake").json()["items"]) == 3
    assert client.get("/api/leads?has_email=false&hide_restricted=false&source=other").json()["items"] == []
    nomail = next(i for i in client.get("/api/leads?has_email=false").json()["items"] if i["company_name"] == "NoMail")
    client.patch(f"/api/opportunities/{nomail['id']}", json={"review_status": "excluded", "exclusion_reason": "test"})
    gone = {i["company_name"] for i in client.get("/api/leads?has_email=false&hide_restricted=false").json()["items"]}
    back = {i["company_name"] for i in client.get("/api/leads?has_email=false&hide_restricted=false&show_excluded=true").json()["items"]}
    assert "NoMail" not in gone and "NoMail" in back                          # excluded listings can be shown again to restore them
    client.patch(f"/api/opportunities/{nomail['id']}", json={"review_status": "new"})
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


# ---------------------------------------------------------------- company websites: general mailboxes stay "review", invitations are honoured
def test_plain_contact_line_on_a_site_does_not_make_a_mailbox_eligible(db):
    run = go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    from app.services import leads as L
    cs = L.attach_emails(db, o, "Contact: hello@acme.example. Press: press@acme.example", "website", "https://acme.example/contact", "acme.example")
    assert [(c.email, c.outreach_eligibility, c.contact_purpose) for c in cs] == [("hello@acme.example", "review_required", "general_business_contact")]


@pytest.mark.parametrize("text,email", [
    ("We are always looking for freelance engineers: write to partners@acme.example to apply.", "partners@acme.example"),
    ("Become one of our freelance partners: email partners@acme.example", "partners@acme.example"),
    ("Freelancers and contractors can contact us at freelance@acme.example", "freelance@acme.example"),
])
def test_website_invitations_to_freelancers_are_eligible_in_pitch_mode(db, text, email):
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    from app.services import leads as L
    cs = L.attach_emails(db, o, text, "website", "https://acme.example/partners", "acme.example", mode="pitch")
    assert [(c.email, c.outreach_eligibility, c.contact_purpose) for c in cs] == [(email, "eligible", "partner_invited")]


def test_pitch_mode_never_treats_a_plain_or_careers_mailbox_as_invited(db):
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    from app.services import leads as L
    cs = L.attach_emails(db, o, "Careers: careers@acme.example  General: hello@acme.example", "website", "https://acme.example/contact", "acme.example", mode="pitch")
    assert {c.email: (c.outreach_eligibility, c.contact_purpose) for c in cs} == {
        "careers@acme.example": ("review_required", "b2b_mailbox"), "hello@acme.example": ("review_required", "b2b_mailbox")}
    assert "unsolicited" in cs[0].eligibility_basis and "opt out" in cs[0].eligibility_basis


# ---------------------------------------------------------------- company sites, application mode: an explicit "send your CV here" counts, a label does not
@pytest.mark.parametrize("text,email,eligible", [
    ("To join LD Talent, please send your resumé (PDF or DOC only) to info@acme.example.", "info@acme.example", True),
    ("Interested? Send your CV to talent@acme.example", "talent@acme.example", True),
    ("To apply, email hello@acme.example", "hello@acme.example", True),
    ("Submit your application to people@acme.example", "people@acme.example", True),
    ("Contact: hello@acme.example", "hello@acme.example", False),
    ("Email: info@acme.example", "info@acme.example", False),
    ("Questions about our product? Write to info@acme.example", "info@acme.example", False),
    ("We do not accept CVs sent to info@acme.example", "info@acme.example", False),
])
def test_on_a_company_site_only_an_explicit_application_invitation_makes_a_mailbox_eligible(db, text, email, eligible):
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    from app.services import leads as L
    cs = L.attach_emails(db, o, text, "website", "https://acme.example/careers", "acme.example")
    assert [c.outreach_eligibility for c in cs] == ["eligible" if eligible else "review_required"]
    if eligible:
        assert cs[0].contact_purpose in ("application_invited", "careers_mailbox")


def test_the_same_resume_sentence_never_makes_a_mailbox_eligible_for_a_pitch(db):
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    from app.services import leads as L
    cs = L.attach_emails(db, o, "Please send your resumé to info@acme.example.", "website", "https://acme.example/careers", "acme.example", mode="pitch")
    assert [(c.outreach_eligibility, c.contact_purpose) for c in cs] == [("review_required", "b2b_mailbox")]   # a job application is not a services pitch


# ---------------------------------------------------------------- reading a site again refreshes what the app decided, never what you set
def test_reading_the_site_again_refreshes_the_apps_own_decision_but_never_one_set_by_hand(db):
    from app.services import contacts as C, leads as L
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example")])})
    o = db.scalar(select(Opportunity))
    url = "https://acme.example/join"
    first = L.attach_emails(db, o, "Contact: info@acme.example", "website", url, "acme.example")[0]
    assert (first.outreach_eligibility, first.contact_purpose) == ("review_required", "general_business_contact")
    invite = "To join Acme, please send your resumé to info@acme.example."
    again = L.attach_emails(db, o, invite, "website", url, "acme.example")[0]
    assert again.id == first.id and (again.outreach_eligibility, again.contact_purpose) == ("eligible", "application_invited")   # the app improved its own call
    C.set_eligibility(db, again, "review_required", "Agreed with the founder by phone: keep as review")
    L.attach_emails(db, o, invite, "website", url, "acme.example")
    db.refresh(again)
    assert again.outreach_eligibility == "review_required" and again.eligibility_basis.startswith("Agreed with the founder")   # your decision stands


def test_an_address_of_another_opportunity_is_not_flipped_by_a_read_in_another_context(db):
    from app.services import leads as L
    go(db, {"fake": FakeAdapter([raw(1, company_name="Acme", company_website="https://acme.example"),
                                 raw(2, company_name="Acme Labs", company_website="https://acme.example")])})
    a, b = db.scalars(select(Opportunity).order_by(Opportunity.id)).all()
    box = L.attach_emails(db, a, "Contact: info@acme.example", "website", "https://acme.example/c", "acme.example", mode="pitch")[0]
    assert (box.outreach_eligibility, box.contact_purpose, box.opportunity_id) == ("review_required", "b2b_mailbox", a.id)
    L.attach_emails(db, b, "To join, please send your resumé to info@acme.example.", "website", "https://acme.example/join", "acme.example")
    db.refresh(box)
    assert (box.outreach_eligibility, box.contact_purpose) == ("review_required", "b2b_mailbox")      # stays as the first context decided


# ---------------------------------------------------------------- a hiring post that says it is CLOSED is not a lead
CLOSED_SAMPLES = ["OpenSanctions | Product Engineer | Berlin / REMOTE | Freelance | CLOSED NOW - STOP SENDING AGENTIC BS",
                  "[CLOSED] Acme | Python engineer | Remote", "Acme | Python engineer | Remote | CLOSED",
                  "Acme | Python engineer | Remote (position filled, thanks!)", "No longer hiring: Acme | Python engineer"]
OPEN_SAMPLES = ["Acme | Python engineer | Remote | closed beta of our new product, apply by email", "Acme | Python engineer | Remote | we close the loop with customers fast",
                "Acme | Python engineer | Remote | Contract"]


@pytest.mark.parametrize("text", CLOSED_SAMPLES)
def test_closed_posts_are_recognised(text):
    from app.adapters import hn_hiring
    from app.services import leads as L
    assert L.CLOSED_POST.search(text) and hn_hiring.CLOSED_POST.search(text)           # the adapter and the clean-up agree


@pytest.mark.parametrize("text", OPEN_SAMPLES)
def test_open_posts_are_not_mistaken_for_closed_ones(text):
    from app.adapters import hn_hiring
    from app.services import leads as L
    assert not L.CLOSED_POST.search(text) and not hn_hiring.CLOSED_POST.search(text)


def test_the_hn_adapter_skips_a_closed_post_and_the_startup_step_closes_stored_ones(db):
    import httpx
    from app.adapters import hn_hiring
    from app.services import leads as L
    from app.types import SearchParams

    def h(req):
        if "tags=story" in str(req.url) and "author_whoishiring" in str(req.url):
            return httpx.Response(200, json={"hits": [{"objectID": "100", "title": "Ask HN: Who is hiring? (October 2026)"}]})
        return httpx.Response(200, json={"nbPages": 1, "hits": [
            {"objectID": "1", "parent_id": 100, "comment_text": "Acme | Python | Remote | CLOSED NOW<p>Python AWS", "created_at_i": 1790000000},
            {"objectID": "2", "parent_id": 100, "comment_text": "Beta | Python | Remote | Contract<p>Python AWS", "created_at_i": 1790000000}]})
    out = hn_hiring.HNHiring(db, httpx.Client(transport=httpx.MockTransport(h))).fetch(SearchParams())
    assert [o.external_id for o in out] == ["2"]
    go(db, {"fake": FakeAdapter([raw(1, source_key="hn_hiring", description="Acme | Python | Remote | CLOSED NOW. " + "Python FastAPI AWS Docker. " * 10),
                                 raw(2, source_key="hn_hiring", description="Beta | Python | Remote | Contract. " + "Python FastAPI AWS Docker. " * 10)])})
    assert L.close_stale_posts(db) == 1 and L.close_stale_posts(db) == 0              # idempotent
    status = {o.company_name: o.listing_status for o in db.scalars(select(Opportunity))}
    assert sorted(status.values()) == ["closed", "open"]


def test_a_closed_listing_is_not_offered_as_a_lead(client, db):
    from app.services import exporter
    go(db, {"fake": FakeAdapter([raw(1, company_name="Open Co", description="Python FastAPI LLM AWS Docker. To apply, email your resume to jobs@open.example. " * 2),
                                 raw(2, company_name="Closed Co", description="Python FastAPI LLM AWS Docker. To apply, email your resume to jobs@closed.example. " * 2)])})
    o = db.scalar(select(Opportunity).where(Opportunity.company_name == "Closed Co"))
    o.listing_status = "closed"; db.commit()
    names = {i["company_name"] for i in client.get("/api/leads?hide_restricted=false").json()["items"]}
    assert names == {"Open Co"}
    leads_sheet = {r["company_name"] for r in exporter.build_combined(db)["leads"]}
    assert leads_sheet == {"Open Co"} and {r["company_name"] for r in exporter.build_combined(db)["opportunities"]} == {"Open Co", "Closed Co"}   # still listed, just not a lead
