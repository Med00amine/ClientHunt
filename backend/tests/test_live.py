import httpx
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.services import emailtable, live
from .conftest import *  # noqa: F401,F403  (fixtures)

NOW = 1793050000


def hn_comment(cid, story, body, age_min=60):
    return {"objectID": str(cid), "parent_id": story, "comment_text": body, "created_at_i": NOW - age_min * 60}


def reddit_post(pid, title, body="", flair="", author="acme_cto", age_min=30):
    return {"kind": "t3", "data": {"id": pid, "title": title, "selftext": body, "link_flair_text": flair, "author": author,
                                   "permalink": f"/r/forhire/comments/{pid}/x/", "created_utc": NOW - age_min * 60, "subreddit": "forhire"}}


FREELANCE_THREAD = {"objectID": "500", "title": "Ask HN: Freelancer? Seeking freelancer? (October 2026)", "num_comments": 40, "created_at_i": NOW - 86400}
HIRING_THREAD = {"objectID": "600", "title": "Ask HN: Who is hiring? (October 2026)", "num_comments": 400, "created_at_i": NOW - 86400}
FREELANCE_COMMENTS = [
    hn_comment(1, 500, "SEEKING FREELANCER | Acme Labs | Remote<p>We need an LLM engineer to build a RAG chatbot in Python. "
                       "Email Jane Doe at jane.doe@acmelabs.io with your portfolio."),
    hn_comment(2, 500, "SEEKING WORK | Berlin | Remote<p>I build LLM apps. Email me: me@freelancer-person.example.net"),
    hn_comment(3, 500, "SEEKING FREELANCER | Paint Co<p>We need a house painter."),        # no query word
]
HIRING_COMMENTS = [
    hn_comment(10, 600, "Rebar | Applied AI Engineer | REMOTE | Contract<p>LLM agents with FastAPI on AWS. Apply: john@withrebar.ai"),
    hn_comment(11, 600, "BigCo | ML Engineer | ONSITE | Full-time<p>Machine learning at scale. jobs@bigco.example.org"),
]
REDDIT = [
    reddit_post("a1", "[Hiring] Python dev for an AI agent", "Need a GPT agent. Budget $2k. Contact sam@shopify-store.co"),
    reddit_post("a2", "[For Hire] ML engineer available", "Hire me: ml@me.example.net"),
    reddit_post("a3", "Need help with OpenAI integration", "DM me", flair="Hiring"),
]
def toot(sid, html, acct="studio@mas.example", tag_age_min=90):
    return {"id": sid, "uri": f"https://mas.example/statuses/{sid}", "url": f"https://mas.example/@studio/{sid}", "content": html,
            "created_at": "2026-10-28T09:00:00.000Z", "account": {"acct": acct}, "sensitive": False, "reblog": None}


MASTODON = [
    toot("m1", "<p>We're looking for a freelance Python developer to build an LLM agent. Contract, ~3 weeks. #hiring</p>"),
    toot("m2", "<p>I'm available for freelance LLM projects! #OpenToWork #hiring</p>"),              # self-promotion
    toot("m3", "<p>BigCorp is hiring a Staff ML Engineer. Full-time, on-site. #hiring</p>"),        # permanent job
]
REMOTIVE = {"jobs": [
    {"id": 7, "url": "https://remotive.com/remote-jobs/7", "title": "Contract ML Engineer", "company_name": "Datafy",
     "description": "<p>Machine learning contract. Email hr@datafy.example.io</p>", "publication_date": "2026-10-27T10:00:00", "job_type": "contract"},
    {"id": 8, "url": "https://remotive.com/remote-jobs/8", "title": "ML Engineer", "company_name": "Perm", "description": "machine learning",
     "publication_date": "2026-10-27T10:00:00", "job_type": "full_time"}]}
JOBICY = {"jobs": [{"id": 9, "url": "https://jobicy.com/jobs/9", "jobTitle": "Part-time Python AI developer", "companyName": "Tiny",
                    "jobDescription": "Python and AI", "pubDate": "2026-10-26 10:00:00", "jobType": ["Part-Time"]}]}


def transport(calls=None, reddit_status=200, listing_status=200):
    def h(req):
        if calls is not None:
            calls.append(str(req.url))
        u, p = req.url, dict(req.url.params)
        if u.host == "hn.algolia.com":
            if p.get("query") == '"Seeking freelancer"':
                return httpx.Response(200, json={"hits": [FREELANCE_THREAD]})
            if p.get("query") == '"Who is hiring"':
                return httpx.Response(200, json={"hits": [HIRING_THREAD]})
            story = p.get("tags", "").split("story_")[-1]
            hits = FREELANCE_COMMENTS if story == "500" else HIRING_COMMENTS if story == "600" else []
            return httpx.Response(200, json={"hits": hits, "nbPages": 1})
        if u.path == "/api/v1/access_token":
            return httpx.Response(reddit_status, json={"access_token": "tok", "expires_in": 3600})
        if u.host == "oauth.reddit.com":
            assert req.headers["Authorization"] == "Bearer tok"
            return httpx.Response(listing_status, json={"data": {"children": REDDIT if "forhire" in u.path else []}})
        if "/api/v1/timelines/tag/" in u.path:
            return httpx.Response(200, json=MASTODON if (u.host, u.path.rsplit("/", 1)[-1]) == ("mastodon.social", "hiring") else [])
        if u.host == "remotive.com":
            return httpx.Response(200, json=REMOTIVE)
        if u.host == "jobicy.com":
            return httpx.Response(200, json=JOBICY)
        if u.host == "himalayas.app":
            return httpx.Response(200, json={"jobs": []})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(h))


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    live.clear_cache()
    monkeypatch.setattr(get_settings(), "reddit_client_id", "id")
    monkeypatch.setattr(get_settings(), "reddit_client_secret", "secret")
    yield
    live.clear_cache()


def test_client_posts_from_all_sources_with_their_emails():
    out = live.search_projects(None, client=transport(), now=NOW)
    by = {r["id"]: r for r in out["items"]}
    assert set(by) == {"hn_freelance:1", "hn_hiring:10", "reddit:a1", "reddit:a3", "mastodon:https://mas.example/statuses/m1",
                       "boards:remotive:7", "boards:jobicy:9"}
    # never collected: people advertising themselves (hn 2, reddit a2, toot m2), full-time jobs (hn 11, toot m3,
    # remotive 8) and posts that match no search word (hn 3)
    jane = by["hn_freelance:1"]["emails"][0]
    assert (jane["name"], jane["email"], jane["company"]) == ("Jane Doe", "jane.doe@acmelabs.io", "Acme Labs")
    assert by["reddit:a1"]["url"] == "https://www.reddit.com/r/forhire/comments/a1/x/" and by["reddit:a1"]["poster"] == "u/acme_cto"
    assert by["reddit:a3"]["emails"] == []
    assert by["boards:remotive:7"]["emails"] == [] and by["boards:remotive:7"]["source_name"] == "Remotive"   # Remotive: no emails
    assert by["mastodon:https://mas.example/statuses/m1"]["source_name"] == "Mastodon #hiring"
    assert {e["email"] for e in out["emails"]} == {"jane.doe@acmelabs.io", "john@withrebar.ai", "sam@shopify-store.co"}
    assert out["errors"] == [] and all(s["ok"] for s in out["sources"].values())
    assert out["sources"]["boards"]["matching"] == 2
    assert not any("freelancer.com" in r["url"] for r in out["items"])


def test_only_email_sorting_and_source_choice():
    c = transport()
    assert all(r["emails"] for r in live.search_projects(None, only_email=True, client=c, now=NOW)["items"])
    hn_only = live.search_projects(None, sources=["hn_freelance"], client=c, now=NOW)
    assert [r["id"] for r in hn_only["items"]] == ["hn_freelance:1"] and set(hn_only["sources"]) == {"hn_freelance"}
    ages = [r["age_minutes"] for r in live.search_projects(None, sort="newest", client=c, now=NOW)["items"]]
    assert ages == sorted(ages)


def test_without_keys_reddit_is_left_out_silently_and_never_contacted(monkeypatch):
    monkeypatch.setattr(get_settings(), "reddit_client_id", "")
    calls: list[str] = []
    out = live.search_projects(None, client=transport(calls), now=NOW)
    assert out["reddit_configured"] is False and "reddit" not in out["sources"] and out["errors"] == []
    assert not any("reddit.com" in c for c in calls)            # robots.txt disallows it: no request at all
    assert out["items"] and all(r["source"] != "reddit" for r in out["items"])


def test_a_busy_source_is_reported_quietly_and_not_asked_again_at_once():
    calls: list[str] = []
    c = transport(calls, listing_status=429)
    listing = lambda: len([x for x in calls if "oauth.reddit.com" in x])  # noqa: E731
    out = live.search_projects(None, client=c, now=NOW)
    assert out["sources"]["reddit"]["ok"] is False and "busy" in out["sources"]["reddit"]["error"]
    assert out["sources"]["hn_freelance"]["ok"] and out["items"]                # the others still answer
    n = listing()
    live.search_projects(None, sources=["reddit"], client=c, now=NOW + 30)
    assert listing() == n                                                       # backs off instead of hammering
    live.search_projects(None, sources=["reddit"], client=c, now=NOW + live.BUSY_SECONDS + 1)
    assert listing() == n + 1


def test_reddit_bad_keys_are_explained():
    out = live.search_projects(None, sources=["reddit"], client=transport(reddit_status=401), now=NOW)
    assert out["items"] == [] and "refused the app credentials" in out["errors"][0]


def test_cache_is_short_lived_and_nothing_is_stored(db):
    tables = __import__("app.db", fromlist=["Base"]).Base.metadata.sorted_tables
    def counts():
        with engine.connect() as con:
            return {t.name: con.execute(text(f"select count(*) from {t.name}")).scalar() for t in tables}
    before = counts()
    calls: list[str] = []
    c = transport(calls)
    live.search_projects(None, sources=["hn_freelance", "hn_hiring", "reddit", "mastodon"], client=c, now=NOW)
    n = len(calls)
    live.search_projects(None, sources=["hn_freelance", "hn_hiring", "reddit", "mastodon"], client=c, now=NOW + 60)
    assert len(calls) == n                                     # served from memory
    live.search_projects(None, sources=["hn_freelance", "hn_hiring", "reddit", "mastodon"], client=c, now=NOW + live.CACHE_SECONDS + 1)
    assert len(calls) > n
    assert counts() == before


def test_boards_keep_their_own_longer_polling_limits():
    calls: list[str] = []
    c = transport(calls)
    live.search_projects(None, sources=["boards"], client=c, now=NOW)
    live.search_projects(None, sources=["boards"], client=c, now=NOW + 2 * 3600)
    assert len([x for x in calls if "remotive.com" in x]) == 1  # Remotive: at most every 6 h
    assert len([x for x in calls if "jobicy.com" in x]) == 2    # Jobicy: hourly


def test_endpoint(client, monkeypatch):
    real = live.search_projects
    monkeypatch.setattr(live, "search_projects", lambda *a, **k: real(*a, client=transport(), now=NOW, **k))
    r = client.get("/api/live/projects?q=llm&sources=hn_freelance,reddit&only_email=true")
    assert r.status_code == 200 and [i["id"] for i in r.json()["items"]] == ["hn_freelance:1"]
    assert client.get("/api/live/projects?sort=bogus").status_code == 422
    assert client.get("/api/live/freelancer").status_code in (404, 405)
    e = client.post("/api/tools/extract-emails", json={"text": "Contact Ali Ben <ali@shop.example> today."})
    assert e.status_code == 200 and e.json()["rows"][0]["name"] == "Ali Ben"
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/live/projects").status_code == 401
    assert client.post("/api/tools/extract-emails", json={"text": "x"}).status_code == 401


@pytest.mark.parametrize("snippet,name,email,company", [
    ("Jane Doe <jane@acme-labs.io>", "Jane Doe", "jane@acme-labs.io", "Acme Labs"),
    ("Please contact Omar Haddad at omar@datawise.ai to apply.", "Omar Haddad", "omar@datawise.ai", "Datawise"),
    ("Company: Northwind Traders\nApply at jobs@northwind.example", "", "jobs@northwind.example", "Northwind Traders"),
    ("Email sara.khan@gmail.com", "Sara Khan", "sara.khan@gmail.com", ""),           # free mail: no company guessed
    ("Questions: hello@tiny-shop.co.uk", "", "hello@tiny-shop.co.uk", "Tiny Shop"),
])
def test_email_table_rows(snippet, name, email, company):
    rows = emailtable.contact_rows(snippet)
    assert [(r["name"], r["email"], r["company"]) for r in rows] == [(name, email, company)]


def test_email_table_skips_non_contact_addresses_and_marks_guesses():
    filler = " We build data tools for retailers and ship every week." * 3
    rows = emailtable.contact_rows(f"noreply@acme.io. Privacy questions: privacy@acme.io.{filler}\nTalk to lee.park@acme.io")
    assert [r["email"] for r in rows] == ["lee.park@acme.io"]
    assert rows[0]["name_from"] == "address" and rows[0]["company_from"] == "domain"


def test_hn_angle_bracket_addresses_survive():
    """HN sends "Kim Lee <kim@bolt.example.io>" escaped; decoding it twice used to turn the address into a tag and drop it."""
    extra = hn_comment(4, 500, "SEEKING FREELANCER | Bolt | Remote<p>LLM agent work. Contact Kim Lee &lt;kim@bolt.example.io&gt;")
    FREELANCE_COMMENTS.append(extra)
    try:
        out = live.search_projects(None, sources=["hn_freelance"], client=transport(), now=NOW)
    finally:
        FREELANCE_COMMENTS.remove(extra)
    kim = next(r for r in out["items"] if r["id"] == "hn_freelance:4")["emails"]
    assert [(e["name"], e["email"], e["company"]) for e in kim] == [("Kim Lee", "kim@bolt.example.io", "Bolt")]
