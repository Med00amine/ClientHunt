import time

import httpx
import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.services import live
from .conftest import *  # noqa: F401,F403  (fixtures)

NOW = 1793050000


def project(pid, title, kind="fixed", lo=100, hi=300, code="USD", rate=1.0, bids=5, age_min=30, status="active",
            nonpublic=False, jobs=("Python", "Machine Learning (ML)"), desc="Build a machine learning pipeline in Python."):
    return {"id": pid, "title": title, "seo_url": f"machine-learning/{title.replace(' ', '-')}-{pid}", "type": kind,
            "status": status, "frontend_project_status": "open", "nonpublic": nonpublic, "deleted": False,
            "budget": {"minimum": lo, "maximum": hi}, "currency": {"code": code, "sign": "$", "exchange_rate": rate},
            "bid_stats": {"bid_count": bids, "bid_avg": 150.0}, "time_submitted": NOW - age_min * 60,
            "jobs": [{"id": i, "name": n} for i, n in enumerate(jobs)], "description": desc, "language": "en", "urgent": False}


def api(payload_by_query):  # noqa: E302
    calls = []
    def h(req):
        calls.append(dict(req.url.params))
        projs = payload_by_query.get(req.url.params["query"], [])
        return httpx.Response(200, json={"status": "success", "result": {"projects": projs, "total_count": len(projs)}})
    return httpx.Client(transport=httpx.MockTransport(h)), calls


@pytest.fixture(autouse=True)
def fresh():
    live.clear_cache()
    yield
    live.clear_cache()


def test_merges_dedupes_shapes_and_computes_fit_and_usd():
    c, calls = api({"llm": [project(1, "LLM agent", lo=500, hi=1500, bids=3, age_min=10),
                            project(2, "Old crowded", bids=120, age_min=600, code="INR", rate=0.012, lo=1000, hi=5000)],
                    "nlp": [project(1, "LLM agent"), project(3, "NLP classifier", kind="hourly", lo=20, hi=40, bids=25)]})
    out = live.search_projects(["llm", "nlp"], client=c, now=NOW)
    assert [x["id"] for x in out["items"]] and {x["id"] for x in out["items"]} == {1, 2, 3}      # id 1 only once
    assert len(calls) == 2 and calls[0]["limit"] == "50" and calls[0]["full_description"] == "true"
    by = {x["id"]: x for x in out["items"]}
    assert by[1]["competition"] == "few bids" and by[3]["competition"] == "some bids" and by[2]["competition"] == "crowded"
    assert by[2]["budget_max_usd"] == 60.0 and by[2]["currency"] == "INR"
    assert by[1]["url"].startswith("https://www.freelancer.com/projects/") and by[1]["age_minutes"] == 10
    assert 0 <= by[1]["fit"] <= 100 and "machine learning" in by[1]["matched_skills"]
    assert "not saved" in out["notice"] and "Bid on Freelancer.com yourself" in out["notice"]


def test_nothing_is_stored_anywhere(db):
    tables = [t for t in __import__("app.db", fromlist=["Base"]).Base.metadata.sorted_tables]
    def counts():
        with engine.connect() as con:
            return {t.name: con.execute(text(f"select count(*) from {t.name}")).scalar() for t in tables}
    before, files_before = counts(), sorted(p.name for p in get_settings().exports_dir.glob("*"))
    c, _ = api({"llm": [project(1, "LLM agent")]})
    live.search_projects(["llm"], client=c, now=NOW)
    assert counts() == before                                                    # no database rows
    assert sorted(p.name for p in get_settings().exports_dir.glob("*")) == files_before   # no export files


def test_cache_is_short_lived_and_below_the_24h_the_terms_allow():
    assert live.CACHE_SECONDS <= 60 * 60 * 24 and live.CACHE_SECONDS == 15 * 60
    c, calls = api({"llm": [project(1, "A")]})
    live.search_projects(["llm"], client=c, now=NOW)
    live.search_projects(["llm"], client=c, now=NOW + 60)
    assert len(calls) == 1                                                       # served from memory
    live.search_projects(["llm"], client=c, now=NOW + live.CACHE_SECONDS + 1)
    assert len(calls) == 2                                                       # refreshed after the TTL


def test_filters_and_sorting():
    c, _ = api({"q": [project(1, "Cheap crowded", lo=10, hi=20, bids=150, age_min=5), project(2, "Good few bids", lo=500, hi=900, bids=2, age_min=90),
                      project(3, "Hourly mid", kind="hourly", lo=20, hi=40, bids=30, age_min=45),
                      project(4, "Closed", status="closed"), project(5, "Hidden", nonpublic=True)]})
    f = lambda **k: [x["id"] for x in live.search_projects(["q"], client=c, now=NOW, **k)["items"]]
    assert set(f()) == {1, 2, 3}                                                  # closed / non-public dropped
    assert f(kind="hourly") == [3] and f(kind="fixed") and 3 not in f(kind="fixed")
    assert set(f(min_usd=100)) == {2, 3}                       # fixed budgets only; hourly projects are not touched
    assert set(f(min_hourly_usd=30)) == {1, 2, 3} and set(f(min_hourly_usd=50)) == {1, 2}
    assert set(f(max_bids=30)) == {2, 3}
    assert f(sort="newest")[0] == 1 and f(sort="fewest_bids")[0] == 2
    w = {x["id"]: x["worth"] for x in live.search_projects(["q"], client=c, now=NOW)["items"]}
    assert w[2] > w[1] and all(0 <= v <= 100 for v in w.values())     # few bids beats crowded, always within 0-100
    assert len(f(limit=2)) == 2


def test_errors_are_explained_not_crashes():
    for status, expect in ((429, "slow down"), (503, "HTTP 503")):
        live.clear_cache()
        c = httpx.Client(transport=httpx.MockTransport(lambda r, s=status: httpx.Response(s)))
        with pytest.raises(live.LiveSourceError, match=expect):
            live.search_projects(["x"], client=c, now=NOW)
    live.clear_cache()
    with pytest.raises(live.LiveSourceError, match="unreadable"):
        live.search_projects(["x"], client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))), now=NOW)
    live.clear_cache()
    def boom(r): raise httpx.ConnectError("down")
    with pytest.raises(live.LiveSourceError, match="Could not reach"):
        live.search_projects(["x"], client=httpx.Client(transport=httpx.MockTransport(boom)), now=NOW)


def test_query_list_is_capped_and_defaults_apply():
    c, calls = api({})
    live.search_projects(["a", "b", "c", "d", "e", "f", "g", "h"], client=c, now=NOW)
    assert len(calls) == live.MAX_QUERIES
    live.clear_cache(); calls.clear()
    live.search_projects(None, client=c, now=NOW)
    assert [x["query"] for x in calls] == live.DEFAULT_QUERIES[:live.MAX_QUERIES]


def test_endpoint_auth_validation_and_error_mapping(client, monkeypatch):
    c, _ = api({"llm": [project(1, "LLM agent")]})
    real = live.search_projects
    monkeypatch.setattr(live, "search_projects", lambda *a, **k: real(*a, client=c, now=NOW, **{x: y for x, y in k.items() if x != "client"}))
    r = client.get("/api/live/freelancer?q=llm")
    assert r.status_code == 200 and r.json()["items"][0]["title"] == "LLM agent"
    assert client.get("/api/live/freelancer?sort=bogus").status_code == 422
    assert client.get("/api/live/freelancer?kind=weird").status_code == 422
    monkeypatch.setattr(live, "search_projects", lambda *a, **k: (_ for _ in ()).throw(live.LiveSourceError("Freelancer.com asked us to slow down.")))
    e = client.get("/api/live/freelancer")
    assert e.status_code == 502 and "slow down" in e.json()["detail"]
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/live/freelancer").status_code == 401
