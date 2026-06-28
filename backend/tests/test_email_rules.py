"""Real snippets from live listings (2026-10): most 'apply by email' addresses on ordinary boards were boilerplate for
accommodation requests, fraud reports or privacy questions. Those must never become leads."""
import pytest
from sqlalchemy import select

from app.models import BusinessContact, Opportunity
from app.services import leads, pipeline
from app.types import SearchParams
from .helpers import FakeAdapter, raw
from .test_csv_and_runs import go

NOT_FOR_APPLYING = [
    "all backgrounds. If you require accommodations during the hiring process, please contact people@hippocraticai.com . Please be aware of recruitment scams",
    "If you need assistance with your application or interviews due to a disability, please let us know at accommodations@plaid.com. Please review our Candidate Privacy",
    "If you require a reasonable accommodation during the application or interview process, please contact recruiting@livekit.io .",
    "If you require reasonable accommodation in order to submit an application, please contact us at: reasonableaccommodations@airbnb.com . Please include your full name",
    "links to apply. Please notify us of any fraudulent representation by sending an email to careers@launchdarkly.com . To apply: https://weworkremotely.com/x",
    "applicant to review our written Affirmative Action Plan. To do so, contact People Ops at hr@launchdarkly.com . Do you need a disability accommodation?",
    "If you would like to report a fraudulent Tebra job posting, please contact us at talentacquisition@tebra.com and consider reporting your experience",
    "accommodate a disability, then please let us know by emailing accommodations@netlify.com accomodations@netlify.com . About Netlify",
    "For privacy requests contact privacy@acme.example. We take data protection seriously.",
    "Press and media enquiries: press@acme.example",
]
MONZO = ("You will have the chance to speak to our recruitment team at various points during your process but if you do have any specific "
         "questions ahead of this please contact us on tech-hiring@monzo.com . Please also use that email to let us know if there's anything "
         "we can do to make your application process easier for you, because of disability, neurodiversity or any other personal reason.")
APPLY = [
    ("To apply, please email your resume to: daneesha.green@tebra.com . Salary: $159,251/year In compliance", "daneesha.green@tebra.com"),
    ("Please send a brief note expressing your interest as well as your resume to engineering@vested.co with the subject “Senior Software Engineer”", "engineering@vested.co"),
    ("To apply, email your resume and GitHub profile to nicholas.hanson@govstar.us Please mention", "nicholas.hanson@govstar.us"),
    ("Email lisa@propellabs.ai with a PR or a link to your work", "lisa@propellabs.ai"),
    ("Or email hello@irashtech.com with a short intro and a project that shows your skills", "hello@irashtech.com"),
    ("CONTACT: careers@onechronos.com -- please send your CV", "careers@onechronos.com"),
    ("Send your resume to jobs@quantumminds.example", "jobs@quantumminds.example"),
]


@pytest.mark.parametrize("text", NOT_FOR_APPLYING)
@pytest.mark.parametrize("strict", [False, True])
def test_addresses_for_other_purposes_are_never_application_addresses(text, strict):
    assert leads.extract_emails(text, strict=strict) == []


@pytest.mark.parametrize("text,email", APPLY)
@pytest.mark.parametrize("strict", [False, True])
def test_real_application_instructions_are_kept_and_marked_invited(text, email, strict):
    got = leads.extract_emails(text, strict=strict)
    assert [g["email"] for g in got] == [email] and got[0]["invited"] is True


def test_real_monzo_text_on_a_board_is_an_accessibility_contact_not_an_application_address():
    assert leads.extract_emails(MONZO, strict=True) == []


def test_strict_mode_needs_clear_apply_wording_but_hn_style_keeps_unclear_ones():
    vague = "Questions about the role? Contact us on tech-hiring@monzo.com. We look forward to hearing from you"
    assert leads.extract_emails(vague, strict=True) == []                                  # an ordinary board: not enough
    got = leads.extract_emails(vague, strict=False)                                         # a hiring post: kept, but not 'invited'
    assert got and got[0]["invited"] is False


def test_role_mailboxes_that_are_never_applications_are_blocked_by_name():
    for local in ("accommodations", "support", "billing", "fraud", "media", "investors", "accessibility", "eeo"):
        assert leads.extract_emails(f"To apply, email your resume to {local}@acme.example") == [], local


def test_board_listing_boilerplate_creates_no_contact_and_no_email_apply_method(db):
    boiler = "We build AI. Python FastAPI LLM AWS Docker. " * 6 + NOT_FOR_APPLYING[3]
    go(db, {"fake": FakeAdapter([raw(1, description=boiler, company_name="Airbnb", engagement_type="contract")])})
    assert db.query(BusinessContact).count() == 0
    o = db.scalar(select(Opportunity))
    assert o.apply_method == "link" and not any("email to apply" in x for x in o.ease_signals)


def test_board_listing_with_real_apply_wording_is_kept_but_hn_boilerplate_still_filtered(db):
    ok = "We build AI. Python FastAPI LLM AWS Docker. " * 6 + APPLY[0][0]
    go(db, {"fake": FakeAdapter([raw(1, description=ok, company_name="Tebra")])})
    c = db.scalar(select(BusinessContact))
    assert c.email == "daneesha.green@tebra.com" and c.outreach_eligibility == "eligible" and c.contact_purpose == "application_invited"


def test_hn_post_with_accommodation_boilerplate_keeps_the_real_address_only(db):
    text = ("Acme | Python AI | Remote. To apply, email your resume to jobs@acme.example. We are an equal opportunity employer. "
            "If you need an accommodation during hiring, contact people@acme.example. Python FastAPI LLM AWS Docker.") * 1
    go(db, {"fake": FakeAdapter([raw(1, source_key="hn_hiring", description=text, company_name="Acme")])})
    assert [c.email for c in db.scalars(select(BusinessContact))] == ["jobs@acme.example"]


# ---------------------------------------------------------------- clean-up of contacts stored by the older, looser rules
def stored(db, email, note, purpose="application_invited", elig="eligible", basis="The hiring company published this address in its own listing to receive applications. Use it only to apply for that role / ask about it.",
           source_type="hiring_post", opp=None):
    c = BusinessContact(email=email, email_norm=email.lower(), domain=email.split("@")[1], source_type=source_type, source_url="https://x.example/job",
                        source_note=note, contact_purpose=purpose, outreach_eligibility=elig, eligibility_basis=basis,
                        opportunity_id=opp.id if opp else None, verified_status="unverified")
    db.add(c); db.commit()
    return c


def test_reclassify_removes_old_wrong_contacts_and_keeps_the_rest(db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="jobicy", company_name="Plaid"), raw(2, source_key="hn_hiring", company_name="Acme")])})
    plaid = db.scalar(select(Opportunity).where(Opportunity.company_name == "Plaid"))
    acme = db.scalar(select(Opportunity).where(Opportunity.company_name == "Acme"))
    bad = stored(db, "accommodations@plaid.com", NOT_FOR_APPLYING[1], opp=plaid)
    good = stored(db, "jobs@acme.example", "To apply, email your resume to jobs@acme.example", opp=acme)
    mine = stored(db, "me@mine.example", "added by me about accommodations", source_type="public_web", purpose="", basis="my own reason")
    hand = stored(db, "founder@acme.example", "Contact: founder@acme.example", purpose="application_invited", elig="eligible", basis="I checked the rules myself", opp=acme)
    res = leads.reclassify_contacts(db)
    left = {c.email for c in db.scalars(select(BusinessContact))}
    assert "accommodations@plaid.com" not in left and {"jobs@acme.example", "me@mine.example", "founder@acme.example"} <= left
    assert res["removed"] == 1
    db.refresh(hand)
    assert hand.eligibility_basis == "I checked the rules myself"                      # hand-set eligibility is never rewritten


def test_reclassify_uses_the_whole_listing_text_not_just_the_short_snippet(db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="jobicy", company_name="Monzo", description="Python FastAPI LLM AWS Docker. " * 10 + MONZO)])})
    o = db.scalar(select(Opportunity))
    stored(db, "tech-hiring@monzo.com", "any specific questions ahead of this please contact us on tech-hiring@monzo.com. Please also use that email", opp=o)
    assert leads.reclassify_contacts(db)["removed"] == 1


def test_reclassify_downgrades_uninvited_addresses_on_boards_and_is_idempotent(db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="wwr", company_name="Monzo")])})
    o = db.scalar(select(Opportunity))
    stored(db, "tech-hiring@monzo.com", "any specific questions ahead of this please contact us on tech-hiring@monzo.com. Please also use that email", opp=o)
    first = leads.reclassify_contacts(db)
    assert first["removed"] == 1                                                         # a board listing needs clear apply wording
    assert leads.reclassify_contacts(db) == {"removed": 0, "kept": 0, "reclassified": 0}


def test_refresh_ease_drops_the_email_bonus_when_the_address_was_removed(db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="wwr", description="Python FastAPI LLM AWS Docker. " * 10, company_name="Airbnb")])})
    o = db.scalar(select(Opportunity))
    o.apply_method, o.ease_score, o.ease_signals = "email", 85.0, ["Company published an email to apply (+30)"]
    o.recommended_action = "Email your application to the address the company published (see Leads); keep it short and specific"
    db.commit()
    assert leads.refresh_ease(db) == 1
    db.refresh(o)
    assert o.apply_method == "link" and o.ease_score < 85 and not any("email to apply" in x for x in o.ease_signals)
    assert not o.recommended_action.startswith("Email your application")
    assert leads.refresh_ease(db) == 0                                                    # stable


def test_lifespan_runs_the_cleanup(client, db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="wwr", company_name="Plaid")])})
    o = db.scalar(select(Opportunity))
    stored(db, "accommodations@plaid.com", NOT_FOR_APPLYING[1], opp=o)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app):                                                                 # startup runs reclassify + refresh
        pass
    db.expire_all()
    assert db.query(BusinessContact).count() == 0


# ---------------------------------------------------------------- the invitation is judged inside the sentence of the address
@pytest.mark.parametrize("text,email,invited", [
    ("Apply via the links above. Questions: contact@vistulo.com.", "contact@vistulo.com", False),
    ("Apply at the link and mention HN somewhere, in your pitch or wherever it fits. joao.pedro@searchatlas.com if you need me, though", "joao.pedro@searchatlas.com", False),
    ("Details at https://x.example/jobs. LinkedIn or contact@ambito.io.", "contact@ambito.io", False),
    ("If you have any questions, feel free to reply here or you can e-mail me at tim@radar.com", "tim@radar.com", True),
    ("Email your CV/LinkedIn and a brief note on how you'd approach GTM for a tech platform to ceo@comograph.com with the subject line", "ceo@comograph.com", True),
    ("To apply: [Edited 10/25, to reflect our new hiring process] Send an email to hiring@sidekicklabs.com with your resume", "hiring@sidekicklabs.com", True),
    ("If interested, shoot an email to jobs@datamint.xyz (or founders@datamint.xyz) with a link", "jobs@datamint.xyz", True),
    ("Apply with CV and a short description of the agents you have shipped: recruiting@strategy.example", "recruiting@strategy.example", True),
    ("Please write us at careers@tahoma.io with your story", "careers@tahoma.io", True),
])
def test_invitation_is_judged_within_its_own_sentence(text, email, invited):
    got = {g["email"]: g["invited"] for g in leads.extract_emails(text, strict=False)}
    assert got[email] is invited


JOB_SEEKER = ("Location: Bangalore, India (IST, UTC+5:30)<p>Remote: Yes<p>Willing to relocate: No<p>Technologies: Python, React<p>"
              "Résumé/CV: https://example.com/cv.pdf<p>Email: someone@icloud.example")


def test_job_seeker_template_is_recognised_but_employers_are_not():
    assert leads.is_job_seeker_post("Willing to relocate: Yes. Technologies: Python") and leads.is_job_seeker_post("SEEKING WORK. Remote. Email me")
    assert leads.is_job_seeker_post("Résumé/CV: https://x.example/cv.pdf") and leads.is_job_seeker_post("Available for hire. Python")
    assert not leads.is_job_seeker_post("Acme | Python AI | Remote. Candidates willing to relocate are welcome. Email jobs@acme.example")
    assert not leads.is_job_seeker_post("We pay for a resume review service. Apply: jobs@acme.example")


def test_hn_adapter_never_collects_job_seeker_posts(db):
    import httpx
    from app.adapters import hn_hiring
    def h(req):
        if "author_whoishiring" in str(req.url):
            return httpx.Response(200, json={"hits": [{"objectID": "100", "title": "Ask HN: Who is hiring? (October 2026)"}]})
        return httpx.Response(200, json={"hits": [
            {"objectID": "1", "parent_id": 100, "comment_text": JOB_SEEKER},
            {"objectID": "2", "parent_id": 100, "comment_text": "Acme | Python AI | Remote<p>To apply, email your resume to jobs@acme.example"}]})
    a = hn_hiring.HNHiring(db, httpx.Client(transport=httpx.MockTransport(h)))
    out = a.fetch(SearchParams())
    assert [o.external_id for o in out] == ["2"]


def test_purge_removes_old_job_seeker_posts_and_their_personal_addresses(db):
    go(db, {"fake": FakeAdapter([raw(1, source_key="hn_hiring", company_name="Acme", description="Python AI. To apply, email your resume to jobs@acme.example " * 3),
                                raw(2, source_key="hn_hiring", company_name="", description=JOB_SEEKER + " Python FastAPI LLM AWS Docker " * 5, title="Location: Bangalore")])})
    assert "someone@icloud.example" in {c.email for c in db.scalars(select(BusinessContact))}   # what the older rules stored
    res = leads.purge_job_seeker_posts(db)
    assert res == {"posts": 1, "contacts": 1}
    assert [o.external_id for o in db.scalars(select(Opportunity))] == ["1"]
    assert "someone@icloud.example" not in {c.email for c in db.scalars(select(BusinessContact))}
    assert leads.purge_job_seeker_posts(db) == {"posts": 0, "contacts": 0}


def test_purge_handles_every_table_that_references_a_listing(db):
    from app.models import Application, Company, Evidence, ProposalDraft, ResearchRun, RunOpportunity
    go(db, {"fake": FakeAdapter([raw(1, source_key="hn_hiring", company_name="Seeker Co", description=JOB_SEEKER + " Python FastAPI LLM AWS Docker " * 5),
                                raw(2, source_key="hn_hiring", company_name="Applied Co", description=JOB_SEEKER + " Python FastAPI LLM AWS Docker " * 5)])})
    a, b = (db.scalar(select(Opportunity).where(Opportunity.external_id == x)) for x in ("1", "2"))
    co = db.get(Company, a.company_id)
    db.add(Evidence(company_id=co.id, opportunity_id=a.id, kind="fact", claim="x", excerpt="x", source_url="https://x.example"))
    db.add(ProposalDraft(opportunity_id=a.id, body="hello"))
    db.add(Application(opportunity_id=b.id))                       # already applied: must be left alone
    db.commit()
    res = leads.purge_job_seeker_posts(db)
    assert res["posts"] == 1
    assert [o.external_id for o in db.scalars(select(Opportunity))] == ["2"]
    assert db.scalar(select(Evidence)).opportunity_id is None      # the company's fact stays, unlinked


def test_startup_still_works_when_a_cleanup_step_fails(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import leads as L
    monkeypatch.setattr(L, "purge_job_seeker_posts", lambda db: (_ for _ in ()).throw(RuntimeError("boom")))
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200              # the app started anyway
