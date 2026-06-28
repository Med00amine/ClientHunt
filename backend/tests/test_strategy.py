import re
from datetime import timedelta
from itertools import count

import pytest

from app.config import get_settings
from app.models import Application, BusinessContact, Company, Conversation, Opportunity, utcnow
from app.portfolio import load_portfolio, save_portfolio
from app.services import playbook, prospects as P, strategy

_n = count(1)


def mk(db, title="Python FastAPI engineer", company="Acme", fit=70.0, ease=40.0, engagement="contract", location="Worldwide",
       source="fake", apply_method="link", skills=("python", "fastapi"), email="", purpose="application_invited",
       elig="eligible", **kw):
    i = next(_n)
    c = db.query(Company).filter_by(name=f"{company} {i}").first() or Company(name=f"{company} {i}", name_norm=f"{company}{i}".lower())
    db.add(c); db.flush()
    o = Opportunity(source_key=source, source_type="api", external_id=str(i), original_url=f"https://example.com/{i}",
                    canonical_url=f"https://example.com/{i}", fingerprint=f"fp{i}", title=f"{title} #{i}", company_id=c.id,
                    company_name=c.name, description="Build it. " * 20, engagement_type=engagement, location_requirements=location,
                    fit_score=fit, ease_score=ease, apply_method=apply_method, required_skills=list(skills), **kw)
    db.add(o); db.flush()
    if email:
        db.add(BusinessContact(email=email, email_norm=email.lower(), domain=email.split("@")[1], name="", company_name=c.name,
                               company_id=c.id, opportunity_id=o.id, source_type="hiring_post", source_url=o.original_url,
                               retrieved_at=utcnow(), outreach_eligibility=elig, contact_purpose=purpose))
    db.commit()
    return o


def ids(section):
    return [i["id"] for i in section["items"]]


def test_empty_database_gives_a_complete_empty_strategy(db):
    d = strategy.build(db)
    t = d["today"]
    assert t["apply_by_email"] == {"total": 0, "items": []} and t["apply_by_link"] == {"total": 0, "items": []}
    assert t["follow_ups"] == {"total": 0, "waiting": 0, "items": []} and t["prospects"]["total"] == 0
    assert d["market"]["fitting_listings"] == 0 and d["market"]["skills"] == [] and d["market"]["hourly"]["median_usd"] is None
    assert d["funnel"]["messages_sent"] == 0 and d["funnel"]["reply_rate_percent"] is None and "at least 10" in d["funnel"]["note"]
    assert d["offers"] and d["channels"] and d["networks"] and d["rules"] and d["why_not_upwork"]["sources"]


def test_today_ranks_contract_first_and_leaves_out_what_you_cannot_or_should_not_do(db):
    full = mk(db, "Staff engineer", fit=95, engagement="full_time", email="jobs@a.example")
    unknown = mk(db, "Backend engineer", fit=90, engagement="unknown", email="jobs@b.example")
    contract = mk(db, "Contract engineer", fit=70, ease=40, engagement="contract", email="jobs@c.example")
    mk(db, "US only", fit=95, engagement="contract", location="US only", email="jobs@d.example")                   # restricted
    mk(db, "Already applied", fit=95, email="jobs@e.example", application_status="submitted")
    mk(db, "Closed", fit=95, email="jobs@f.example", listing_status="closed")
    mk(db, "Weak fit", fit=20, email="jobs@g.example")
    mk(db, "Excluded", fit=95, email="jobs@h.example", review_status="excluded")
    t = strategy.build(db)["today"]
    assert ids(t["apply_by_email"]) == [contract.id, unknown.id, full.id] and t["apply_by_email"]["total"] == 3
    first = t["apply_by_email"]["items"][0]
    assert first["emails"][0]["email"] == "jobs@c.example" and first["emails"][0]["source_url"] and first["location_check"] == "worldwide"
    assert first["has_draft"] is False


def test_a_contract_lead_to_review_beats_an_employment_lead_with_an_eligible_address(db):
    employment = mk(db, "Senior engineer", fit=90, engagement="full_time", email="jobs@a.example")                               # eligible, but employment
    contract = mk(db, "Contract engineer", fit=40, engagement="contract", email="hello@b.example", elig="review_required", purpose="general_business_contact")
    assert ids(strategy.build(db)["today"]["apply_by_email"]) == [contract.id, employment.id]


def test_eligible_addresses_come_before_review_addresses_of_the_same_kind(db):
    review = mk(db, "A", fit=90, email="hello@x.example", elig="review_required", purpose="general_business_contact")
    eligible = mk(db, "B", fit=60, email="jobs@y.example")
    assert ids(strategy.build(db)["today"]["apply_by_email"]) == [eligible.id, review.id]


def test_link_list_holds_contract_work_without_an_email_only(db):
    link = mk(db, "Contract via link", engagement="freelance", apply_method="link")
    unknown_method = mk(db, "Part time", engagement="part_time", apply_method="unknown")
    mk(db, "Says email, none stored", engagement="contract", apply_method="email")
    mk(db, "Employment", engagement="full_time", apply_method="link")
    mk(db, "Has a mailbox", engagement="contract", email="jobs@z.example")
    t = strategy.build(db)["today"]
    assert set(ids(t["apply_by_link"])) == {link.id, unknown_method.id} and t["apply_by_link"]["total"] == 2
    assert t["apply_by_email"]["total"] == 1


def test_a_pitch_mailbox_of_the_same_company_is_never_shown_as_an_application_address(db):
    o = mk(db, "Contract engineer", email="jobs@acme.example")
    db.add(BusinessContact(email="hello@acme.example", email_norm="hello@acme.example", domain="acme.example", company_name=o.company_name,
                           company_id=o.company_id, opportunity_id=None, source_type="company_website", source_url="https://acme.example/contact",
                           retrieved_at=utcnow(), outreach_eligibility="review_required", contact_purpose="b2b_mailbox"))
    db.commit()
    item = strategy.build(db)["today"]["apply_by_email"]["items"][0]
    assert [e["email"] for e in item["emails"]] == ["jobs@acme.example"]


def test_a_listing_with_a_draft_says_so(db):
    from app.models import ProposalDraft
    o = mk(db, email="jobs@acme.example")
    db.add(ProposalDraft(opportunity_id=o.id, version=1, body="x", status="draft", generator="template"))
    db.commit()
    assert strategy.build(db)["today"]["apply_by_email"]["items"][0]["has_draft"] is True


def test_follow_ups_follow_the_day_4_day_10_and_stop_rhythm(db):
    now = utcnow()

    def applied(days, title, sent=0, inbound=False, status="submitted"):
        o = mk(db, title, application_status="submitted")
        a = Application(opportunity_id=o.id, status=status, submitted_at=now - timedelta(days=days))
        db.add(a); db.flush()
        for _ in range(sent):
            db.add(Conversation(application_id=a.id, direction="out", summary="follow-up"))
        if inbound:
            db.add(Conversation(application_id=a.id, direction="in", summary="they replied"))
        db.commit()
        return o

    applied(2, "too early")
    first = applied(5, "day five")
    last = applied(11, "day eleven")
    close_old = applied(25, "day twenty-five")
    close_sent = applied(8, "two follow-ups sent", sent=2)
    applied(6, "one follow-up sent, early", sent=1)                  # already followed up and not yet day 10: waiting
    applied(30, "they answered", inbound=True)                       # a conversation now, not a follow-up
    applied(30, "status replied", status="replied")                  # not 'submitted': out of this list
    fu = strategy.build(db, now)["today"]["follow_ups"]
    stages = {i["opportunity_id"]: i["stage"] for i in fu["items"]}
    assert stages == {first.id: "first", last.id: "last", close_old.id: "close", close_sent.id: "close"}
    assert fu["total"] == 4 and fu["waiting"] == 2
    assert [i["days"] for i in fu["items"]] == sorted((i["days"] for i in fu["items"]), reverse=True)


def test_prospect_lists_split_into_to_research_and_ready(db):
    a = P.add_prospect(db, "https://new.example", "New", "company")
    b = P.add_prospect(db, "https://done.example", "Done", "agency")
    c = P.add_prospect(db, "https://sent.example", "Sent", "company")
    d = P.add_prospect(db, "https://failed.example", "Failed", "company")
    b.research_status, b.ease_score = "done", 55.0
    c.research_status, c.application_status = "done", "submitted"
    d.research_status = "failed"
    db.add(BusinessContact(email="hello@done.example", email_norm="hello@done.example", domain="done.example", company_name="Done",
                           opportunity_id=b.id, source_type="company_website", source_url="https://done.example/contact",
                           retrieved_at=utcnow(), outreach_eligibility="review_required", contact_purpose="b2b_mailbox"))
    db.commit()
    p = strategy.build(db)["today"]["prospects"]
    assert p["total"] == 4 and p["contacted"] == 1
    assert set(ids(p["to_research"])) == {a.id, d.id} and ids(p["ready"]) == [b.id]
    ready = p["ready"]["items"][0]
    assert ready["mailboxes"] == 1 and ready["category"] == "agency" and ready["offer"] and ready["need_score"] == 55


def test_portfolio_section_lists_what_is_not_verified(db):
    pf = strategy.build(db)["today"]["portfolio"]
    assert pf["verified"] == 1 and {u["id"] for u in pf["unverified"]} == {"rag-project", "churn-api", "vocality-soni2"}


def test_market_counts_skills_and_marks_the_ones_without_verified_evidence(db):
    for _ in range(3):
        mk(db, skills=("python", "aws"))
    mk(db, skills=("python",), engagement="unknown")
    mk(db, skills=("aws",), location="US only")           # restricted: not part of your market
    mk(db, skills=("aws",), fit=10)                       # does not fit you
    m = strategy.build(db)["market"]
    assert m["fitting_listings"] == 4 and m["engagement"] == {"contract": 3, "unknown": 1}
    by = {s["skill"]: s for s in m["skills"]}
    assert by["python"]["count"] == 4 and by["python"]["share_percent"] == 100 and by["python"]["verified_evidence"] is True
    assert by["aws"]["count"] == 3 and by["aws"]["share_percent"] == 75 and by["aws"]["verified_evidence"] is False   # none of your verified work shows AWS
    assert m["sources"] == [{"source": "fake", "fitting": 4, "contract_or_freelance": 3, "with_email": 0}]


def test_sources_are_ranked_by_published_emails_first(db):
    mk(db, source="board", engagement="contract")
    mk(db, source="board", engagement="contract")
    mk(db, source="hn", engagement="unknown", email="jobs@a.example")
    assert [s["source"] for s in strategy.build(db)["market"]["sources"]] == ["hn", "board"]


@pytest.mark.parametrize("n,has_median", [(0, False), (7, False), (8, True), (12, True)])
def test_an_hourly_rate_is_only_reported_with_enough_listings(db, n, has_median):
    for k in range(n):
        mk(db, rate_type="hourly", currency="USD", budget_min=20 + k, budget_max=30 + k)
    mk(db, rate_type="hourly", currency="EUR", budget_min=500, budget_max=900)      # another currency: not mixed in
    mk(db, rate_type="annual", currency="USD", budget_min=90000, budget_max=120000)
    h = strategy.build(db)["market"]["hourly"]
    assert h["n"] == n and (h["median_usd"] is not None) is has_median
    if has_median:
        assert h["min_usd"] == 25 and "Median of the midpoints" in h["note"]
    else:
        assert "too few" in h["note"] and h["min_usd"] is None


def test_funnel_rates_appear_only_after_ten_messages(db):
    def send(status="submitted", inbound=False, source="fake"):
        o = mk(db, source=source, application_status=status)
        a = Application(opportunity_id=o.id, status=status)
        db.add(a); db.flush()
        if inbound:
            db.add(Conversation(application_id=a.id, direction="in", summary="hi"))
        db.commit()
    for _ in range(4):
        send()
    send("replied"); send("won"); send(inbound=True)
    f = strategy.build(db)["funnel"]
    assert (f["messages_sent"], f["replies"], f["won"]) == (7, 3, 1) and f["reply_rate_percent"] is None and f["win_rate_percent"] is None
    for _ in range(3):
        send(source="prospect")
    f = strategy.build(db)["funnel"]
    assert f["messages_sent"] == 10 and f["pitches"] == 3 and f["reply_rate_percent"] == 30 and f["win_rate_percent"] == 10
    assert "Measured" in f["note"]


def test_an_offer_is_ready_only_when_a_verified_item_shows_its_defining_skill(db):
    offers = {o["key"]: o for o in strategy.build(db)["offers"]}
    assert {k for k, o in offers.items() if o["ready"]} == {"document_extraction", "workflow_automation", "subcontract_capacity"}
    assert offers["rag_assistant"]["ready"] is False and offers["rag_assistant"]["core_skill"] == "rag" and offers["aws_deployment"]["ready"] is False
    assert "network_application" not in offers
    items = load_portfolio()
    for i in items:
        if i["id"] == "rag-project":
            i["verified"] = True
    save_portfolio(items)
    offers = {o["key"]: o for o in strategy.build(db)["offers"]}
    assert offers["rag_assistant"]["ready"] is True and offers["rag_assistant"]["backed_by"] == ["RAG project"]
    assert strategy.build(db)["offers"][-1]["ready"] is False                         # ready offers are listed first


def test_income_is_arithmetic_on_stated_assumptions(db):
    inc = strategy.build(db)["income"]
    assert inc["hours_per_month"] == 50 and inc["billable_hours"] == 30
    rows = {r["target"]: r for r in inc["rows"]}
    assert rows[1000]["hourly_needed"] == 33 and rows[3000]["hourly_needed"] == 100
    assert {p["price"]: p["count"] for p in rows[1000]["projects"]} == {100: 10, 250: 4, 500: 2, 1000: 1, 2000: 1}
    assert "not a forecast" in inc["note"]


def test_the_playbook_gives_a_source_and_a_date_for_every_outside_fact():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", playbook.CHECKED)
    for n in playbook.NETWORKS:
        assert n["url"].startswith("https://") and n["quote"] and n["how_to_apply"] and n["location"], n["name"]
        if n["email"]:
            assert n["email"] in n["quote"], n["name"]                    # an address is only listed if the page itself says it
    for item in playbook.NOT_NOW + playbook.WHY_NOT_UPWORK["sources"]:
        assert item["url"].startswith("https://")
    assert sum(c["share"] for c in playbook.CHANNELS) == 100
    assert {c["tab"] for c in playbook.CHANNELS} <= {"Leads", "Live projects", "Prospects", "Strategy", "Settings"}
    fu = playbook.FOLLOW_UP
    assert fu["first_after_days"] < fu["last_after_days"] < fu["close_after_days"]


def test_api_serves_the_strategy_behind_the_password(client, monkeypatch):
    d = client.get("/api/strategy").json()
    assert set(d) >= {"today", "market", "funnel", "offers", "income", "channels", "networks", "message", "follow_up", "week",
                      "spend_plan", "rules", "why_not_upwork", "checked", "generated_at"}
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/strategy").status_code == 401
