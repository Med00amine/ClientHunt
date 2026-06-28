import httpx
import pytest
from sqlalchemy import select

from app.adapters import jobicy, pythonorg, wwr
from app.adapters.base import AdapterError, AdapterUnavailable, infer_engagement, origin_if_company_site, registry, to_naive_utc
from app.models import Source, utcnow
from app.services import pipeline, presets
from app.types import SearchParams
from .helpers import raw


def adapter(cls, handler, db):
    a = cls(db, httpx.Client(transport=httpx.MockTransport(handler)))
    a.sleep = lambda s: None
    return a


# ---------------------------------------------------------------- engagement wording (real boilerplate examples)
@pytest.mark.parametrize("title,desc,expected", [
    ("Senior Independent AI Engineer / Architect", "Remote | Americas", "contract"),
    ("Software Engineer, AI Coding Tasks (Contract)", "Headquarters: Australia", "contract"),
    ("Freelance Marketo Email Engineer", "", "contract"),
    ("Senior Independent Software Developer ($90-$170/hr)", "", "contract"),
    ("Anthropic STEM Fellow", "Residency. This is a fixed-term contract position. Fellows are engaged", "contract"),
    ("Python Developer", "We are looking for a freelance Python developer for a 3-month project", "contract"),
    ("Staff Engineer", "Part-time, 20 hours a week, remote.", "part_time"),
    ("Backend Engineer", "Full-time position. Remote across Europe.", "full_time"),
    # boilerplate that must NOT make a full-time post look like a contract
    ("Frontend Engineer, Ads", "x " * 200 + "We will evaluate your application for employment or an independent contractor role, as applicable.", "unknown"),
    ("Senior Software Engineer", "x " * 200 + "The pay range may include an hourly rate, annual salary, or on-target earnings.", "unknown"),
    ("Platform Engineer", "x " * 200 + "Benefits include health, dental, vision, short-term disability and life insurance. Full-time.", "full_time"),
    ("Infrastructure Engineer", "serving millions of page views per hour. " + "x " * 200, "unknown"),
    ("Engineer", "No contractors or agencies please. Full-time only.", "full_time"),
])
def test_engagement_inference_is_precise(title, desc, expected):
    assert infer_engagement(title, desc) == expected


def test_helpers():
    assert origin_if_company_site("http://a.team/ai-jobs?utm_source=wwr") == "http://a.team"
    assert origin_if_company_site("https://boards.greenhouse.io/acme/jobs/1") == ""
    assert origin_if_company_site("https://www.linkedin.com/company/x") == ""
    assert origin_if_company_site("javascript:alert(1)") == ""
    assert to_naive_utc("2026-10-26T16:46:54+02:00").hour == 14
    assert to_naive_utc("Mon, 26 Oct 2026 10:00:00 +0000").day == 26
    assert to_naive_utc(1793050243).year == 2026
    assert to_naive_utc("garbage") is None and to_naive_utc(None) is None


# ---------------------------------------------------------------- Jobicy
JOBICY = {"success": True, "jobs": [
    {"id": 1, "url": "https://jobicy.com/jobs/1-ml-engineer", "jobTitle": "ML Engineer (contract)", "companyName": "Acme",
     "jobIndustry": ["Data Science"], "jobType": ["Contract"], "jobGeo": "Anywhere", "jobLevel": "Senior",
     "jobDescription": "<p>Build <b>PyTorch</b> models</p><script>alert(1)</script>", "pubDate": "2026-10-26T16:46:54+00:00",
     "salaryMin": "50", "salaryMax": "70", "salaryCurrency": "USD", "salaryPeriod": "hourly"},
    {"id": 2, "url": "https://jobicy.com/jobs/2-backend", "jobTitle": "Backend Engineer", "companyName": "Beta",
     "jobIndustry": ["Software Engineering"], "jobType": ["Full-Time", "Contract"], "jobGeo": ["Europe", "UK"],
     "jobExcerpt": "Python APIs", "pubDate": "2026-10-25T10:00:00+00:00", "salaryMin": "0", "salaryMax": "0", "salaryCurrency": ""},
    {"id": 3, "url": "https://jobicy.com/jobs/3-fulltime", "jobTitle": "Engineer", "companyName": "Gamma", "jobType": ["Full-Time"],
     "jobGeo": "USA", "jobDescription": "<p>Python</p>", "pubDate": "2026-10-24T10:00:00+00:00",
     "salaryMin": "90000", "salaryMax": "120000", "salaryCurrency": "USD", "salaryPeriod": "yearly"},
    {"id": 1, "url": "https://jobicy.com/jobs/1-ml-engineer", "jobTitle": "duplicate id", "companyName": "Acme"},
]}


def test_jobicy_parses_types_salary_geo_and_dedupes(db):
    calls = []
    def h(req):
        calls.append(dict(req.url.params))
        return httpx.Response(200, json=JOBICY)
    out = adapter(jobicy.Jobicy, h, db).fetch(SearchParams(keywords=["machine learning", "llm"]))
    assert [c["tag"] for c in calls] == ["machine learning", "llm"] and all(c["count"] == "100" for c in calls)
    assert [o.external_id for o in out] == ["1", "2", "3"]               # duplicate id dropped across queries too
    a, b, c = out
    assert a.engagement_type == "contract" and (a.budget_min, a.budget_max, a.currency, a.rate_type) == (50, 70, "USD", "hourly")
    assert "alert" not in a.description and "PyTorch" in a.description and a.location_requirements == "Anywhere"
    assert a.url == "https://jobicy.com/jobs/1-ml-engineer" and a.posted_at.year == 2026   # link back to Jobicy itself
    assert b.engagement_type == "contract" and b.location_requirements == "Europe, UK" and b.budget_min is None
    assert c.engagement_type == "full_time" and c.rate_type == "annual"


def test_jobicy_error_response_and_cache(db):
    n = {"c": 0}
    def h(req):
        n["c"] += 1
        return httpx.Response(200, json={"success": False, "message": "bad"})
    with pytest.raises(AdapterError):
        adapter(jobicy.Jobicy, h, db).fetch(SearchParams(keywords=["x"]))
    n["c"] = 0
    a = adapter(jobicy.Jobicy, lambda r: (n.__setitem__("c", n["c"] + 1), httpx.Response(200, json=JOBICY))[1], db)
    a.fetch(SearchParams(keywords=["python"])); a.fetch(SearchParams(keywords=["python"]))
    assert n["c"] == 1   # hourly polling limit: second call served from the cache


def test_an_error_reply_is_retried_and_never_cached(db):
    n = {"c": 0}
    def h(req):
        n["c"] += 1
        return httpx.Response(200, json={"success": False, "message": "try later"})
    a = adapter(jobicy.Jobicy, h, db)
    with pytest.raises(AdapterError):
        a.fetch(SearchParams(keywords=["python"]))
    assert n["c"] == 3                                            # retried 3 times
    from app.models import HttpCache
    assert db.query(HttpCache).count() == 0                        # and the bad reply was not cached
    a.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=JOBICY)))
    assert len(a.fetch(SearchParams(keywords=["python"]))) == 3   # next call works immediately


# ---------------------------------------------------------------- We Work Remotely
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss"><channel><title>WWR</title>
<item><title>A.Team: Senior Independent AI Engineer / Architect</title><region>Anywhere in the World</region>
<category>Full-Stack Programming</category>
<description>&lt;img src="x.gif" /&gt; &lt;p&gt;&lt;strong&gt;Headquarters:&lt;/strong&gt; NYC &lt;br /&gt;&lt;strong&gt;URL:&lt;/strong&gt; &lt;a href="http://a.team/ai-jobs?utm_source=wwr&amp;amp;utm_medium=post"&gt;http://a.team/ai-jobs&lt;/a&gt; &lt;/p&gt;&lt;p&gt;Build LLM products with Python.&lt;/p&gt;</description>
<pubDate>Mon, 26 Oct 2026 10:00:00 +0000</pubDate><guid>https://weworkremotely.com/remote-jobs/a-team-senior-ai</guid><link>https://weworkremotely.com/remote-jobs/a-team-senior-ai</link></item>
<item><title>Acme: Backend Engineer</title><region>USA Only</region><category>Back-End Programming</category>
<description>&lt;p&gt;Full-time. &lt;a href="https://boards.greenhouse.io/acme"&gt;apply&lt;/a&gt;&lt;/p&gt;</description>
<pubDate>Sun, 25 Oct 2026 10:00:00 +0000</pubDate><guid>https://weworkremotely.com/remote-jobs/acme-backend</guid><link>https://weworkremotely.com/remote-jobs/acme-backend</link></item>
</channel></rss>"""


def test_wwr_parses_company_region_website_and_dedupes_feeds(db):
    seen = []
    def h(req):
        seen.append(req.url.path)
        return httpx.Response(200, text=RSS, headers={"content-type": "application/rss+xml"})
    out = adapter(wwr.WeWorkRemotely, h, db).fetch(SearchParams())
    assert len(seen) == len(wwr.FEEDS) and len(out) == 2                      # same items in 5 feeds -> 2 listings
    a, b = out
    assert (a.company_name, a.title) == ("A.Team", "Senior Independent AI Engineer / Architect")
    assert a.company_website == "http://a.team" and a.company_website_source == "listing_field"
    assert a.engagement_type == "contract" and a.location_requirements == "Anywhere in the World"
    assert a.posted_at.day == 26 and "Build LLM products" in a.description and "<" not in a.description
    assert b.company_website == "" and b.engagement_type == "full_time" and b.location_requirements == "USA Only"


def test_wwr_rejects_hostile_xml(db):
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>'
            '<rss><channel><item><title>&lol2;</title></item></channel></rss>')
    with pytest.raises(AdapterError):
        adapter(wwr.WeWorkRemotely, lambda r: httpx.Response(200, text=bomb), db).fetch(SearchParams())


def test_wwr_garbage_is_an_error_not_a_crash(db):
    with pytest.raises(AdapterError):
        adapter(wwr.WeWorkRemotely, lambda r: httpx.Response(200, text="<html>not a feed"), db).fetch(SearchParams())


# ---------------------------------------------------------------- python.org
PYRSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Python Jobs</title>
<item><title>AI Engineer, webbyfox consultancy</title><link>https://www.python.org/jobs/8184/</link><guid>https://www.python.org/jobs/8184/</guid>
<description>London, UK&lt;p&gt;Design LLM-powered features in Python.&lt;/p&gt;</description></item>
<item><title>Senior Software Engineer — Python, React &amp; AI, Camden Kelly Staffing</title><link>https://www.python.org/jobs/8181/</link>
<guid>https://www.python.org/jobs/8181/</guid><description>Remote, None, Global&lt;p&gt;Contractor role, 6 months.&lt;/p&gt;</description></item>
</channel></rss>"""


def test_pythonorg_parses_title_company_location_remote(db):
    out = adapter(pythonorg.PythonJobBoard, lambda r: httpx.Response(200, text=PYRSS), db).fetch(SearchParams())
    a, b = out
    assert (a.title, a.company_name, a.external_id, a.location_requirements) == ("AI Engineer", "webbyfox consultancy", "8184", "London, UK")
    assert a.remote_status == "unknown" and a.posted_at is None
    assert (b.title, b.company_name) == ("Senior Software Engineer — Python, React & AI", "Camden Kelly Staffing")
    assert b.remote_status == "remote" and b.engagement_type == "contract"


# ---------------------------------------------------------------- filters, presets, seeds
def test_strict_engagement_filter():
    strict = SearchParams(strict_engagement=True, engagement_types=["contract", "freelance", "part_time"], remote_only=False, posted_within_days=None)
    assert not pipeline.passes_filters(raw(1, engagement_type="unknown"), strict)[0]
    assert pipeline.passes_filters(raw(1, engagement_type="contract"), strict)[0]
    assert not pipeline.passes_filters(raw(1, engagement_type="full_time"), strict)[0]
    lax = SearchParams(engagement_types=["contract"], remote_only=False, posted_within_days=None)
    assert pipeline.passes_filters(raw(1, engagement_type="unknown"), lax)[0]       # default keeps unknown


def test_new_sources_and_ai_ml_preset_are_seeded(db):
    from app.models import SearchProfile
    keys = {s.key: s for s in db.scalars(select(Source))}
    for k in ("jobicy", "wwr", "pythonorg", "freelancer_live"):
        assert k in keys
    assert keys["freelancer_live"].kind == "live" and keys["freelancer"].kind == "unavailable"
    assert "copy or store" in keys["freelancer_live"].notes
    prof = {p.name: p for p in db.scalars(select(SearchProfile))}
    ai = prof["AI / ML projects: contract & freelance only"]
    assert ai.params["strict_engagement"] is True and ai.params["min_fit"] == 35.0
    assert ai.params["country"] == "Tunisia"          # roles restricted to other countries are dropped up front
    assert {"jobicy", "wwr", "pythonorg", "hn_hiring"} <= set(ai.params["sources"])
    assert len(prof) >= 7


def test_seed_updates_source_notes_but_keeps_enabled_choice(db):
    row = db.scalar(select(Source).where(Source.key == "jobicy"))
    row.notes, row.enabled = "stale", False
    db.commit()
    presets.seed(db)
    db.refresh(row)
    assert row.notes != "stale" and row.enabled is False


def test_freelancer_stored_adapter_refuses_and_points_to_live_view(db):
    a = registry["freelancer"](db)
    with pytest.raises(AdapterUnavailable) as e:
        a.fetch(SearchParams())
    assert "Live projects" in str(e.value) and "store" in str(e.value)


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "file:///etc/passwd", "ftp://x.example/a", "//evil.example/x", " "])
def test_pipeline_rejects_non_http_links(db, bad):
    from app.models import ResearchRun
    run = ResearchRun(params={}); db.add(run); db.commit()
    p = SearchParams(min_fit=0, remote_only=False, posted_within_days=None)
    st = pipeline.process(db, [raw(1, url=bad), raw(2, url="https://ok.example/2")], p, run.id)
    assert st["stored"] == 1 and st["rejected_irrelevant"] == 1


# ---------------------------------------------------------------- precision fixes found with live Jobicy / Himalayas data
def test_jobicy_decodes_html_entities(db):
    data = {"success": True, "jobs": [{"id": 9, "url": "https://jobicy.com/jobs/9", "jobTitle": "AI &amp; Data Engineer", "companyName": "Zone &#038; Co",
                                       "jobType": ["Contract"], "jobGeo": "Czechia", "jobDescription": "<p>Python</p>", "pubDate": "2026-10-26T10:00:00+00:00"}]}
    out = adapter(jobicy.Jobicy, lambda r: httpx.Response(200, json=data), db).fetch(SearchParams(keywords=["ai"]))
    assert out[0].company_name == "Zone & Co" and out[0].title == "AI & Data Engineer"


@pytest.mark.parametrize("title,capped", [
    ("Senior Performance Marketer (Full Remote - Spain)", True), ("AI Lead Creative", True), ("Freelance - Spanish Data Annotation Specialist", True),
    ("Clinical AI Nurse SME (Part time contract)", True), ("AI QA Trainer – LLM Evaluation", True), ("Technical Account Manager", True),
    ("Applied AI Engineer – OCR", False), ("Lead Machine Learning Scientist, Search", False), ("Data Scientist", False),
    ("Software Engineer, AI Coding Tasks (Contract)", False), ("MLOps Engineer", False), ("Python Developer", False),
    ("Growth Marketing Engineer (AI-First)", False), ("Research Scientist, LLM", False),
])
def test_role_check_uses_role_words_not_topics(title, capped):
    from app.scoring import score
    r = score(raw(1, title=title, description="Python FastAPI AWS LLM RAG Docker machine learning " * 20), None, [])
    assert (r["total"] <= 30) == capped, (title, r["total"], r["explanation"][:120])


@pytest.mark.parametrize("loc,expected", [
    ("UK", "restricted"), ("Czechia", "restricted"), ("Spain", "restricted"), ("USA", "restricted"), ("Canada,  USA", "restricted"),
    ("LATAM,  Argentina", "restricted"), ("Germany; France", "restricted"), ("United Kingdom", "restricted"), ("Hong Kong", "restricted"),
    ("Europe", "compatible"), ("EMEA,  LATAM,  Canada, USA", "compatible"), ("Tunisia", "compatible"), ("Egypt, Morocco", "compatible"),
    ("Anywhere", "worldwide"), ("Anywhere in the World", "worldwide"), ("Worldwide (any time zone)", "worldwide"),
    ("Remote", "unknown"), ("", "unknown"), ("Mars", "unknown"), ("UK or Tunisia", "compatible"),
])
def test_bare_country_lists_are_restrictions(loc, expected):
    from app.scoring import geo_status
    assert geo_status(loc) == expected, loc


def test_country_filter_drops_roles_restricted_elsewhere_but_keeps_open_ones():
    p = SearchParams(country="Tunisia", remote_only=False, posted_within_days=None)
    keep = ["Worldwide (any time zone)", "Anywhere in the World", "Europe", "EMEA", "", "Remote", "Africa", "UK or Tunisia"]
    drop = ["UK", "Czechia", "Only: Poland; Time zones: UTC+1", "US only", "Canada,  USA", "LATAM,  Argentina", "Remote (U.S. Eastern/Central Time)"]
    for loc in keep:
        assert pipeline.passes_filters(raw(1, location_requirements=loc), p)[0], loc
    for loc in drop:
        assert not pipeline.passes_filters(raw(1, location_requirements=loc), p)[0], loc


# ---------------------------------------------------------------- Real Work From Anywhere + Remote OK inference
RWFA = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Remote Jobs - Real Work From Anywhere</title>
<item><title><![CDATA[Solutions Architect at LiveKit]]></title><description><![CDATA[<h2>ABOUT</h2><p>Build AI agents in Python.</p>]]></description>
<link>https://www.realworkfromanywhere.com/jobs/solutions-architect-livekit</link><guid>https://www.realworkfromanywhere.com/jobs/solutions-architect-livekit</guid><pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title><![CDATA[Freelance ML Engineer at Acme Labs]]></title><description><![CDATA[<p>Freelance machine learning work.</p>]]></description>
<link>https://www.realworkfromanywhere.com/jobs/ml-acme</link><guid>https://www.realworkfromanywhere.com/jobs/ml-acme</guid><pubDate>Sun, 25 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title><![CDATA[Role without a company]]></title><description><![CDATA[x]]></description><link>https://www.realworkfromanywhere.com/jobs/x</link><guid>x</guid></item>
</channel></rss>"""


def test_rwfa_parses_role_company_and_marks_everything_worldwide(db):
    from app.adapters import rwfa
    out = adapter(rwfa.RealWorkFromAnywhere, lambda r: httpx.Response(200, text=RWFA), db).fetch(SearchParams())
    a, b, c = out
    assert (a.title, a.company_name) == ("Solutions Architect", "LiveKit") and "Build AI agents" in a.description
    assert a.location_requirements.startswith("Worldwide") and a.remote_status == "remote" and a.posted_at.day == 26
    assert (b.title, b.company_name, b.engagement_type) == ("Freelance ML Engineer", "Acme Labs", "contract")
    assert (c.title, c.company_name) == ("Role without a company", "")
    from app.scoring import geo_status
    assert geo_status(a.location_requirements) == "worldwide"          # open to Tunisia


def test_remoteok_infers_contract_wording(db):
    from app.adapters import remoteok
    data = [{"legal": "x"}, {"id": 1, "position": "Freelance Python Developer", "company": "A", "url": "https://remoteok.com/1", "description": "<p>x</p>", "tags": []},
            {"id": 2, "position": "Backend Engineer", "company": "B", "url": "https://remoteok.com/2", "description": "<p>Full-time role</p>", "tags": []}]
    out = adapter(remoteok.RemoteOK, lambda r: httpx.Response(200, json=data), db).fetch(SearchParams())
    assert [o.engagement_type for o in out] == ["contract", "full_time"]


def test_feeds_with_bare_ampersands_and_control_chars_still_parse(db):
    from app.adapters import rwfa
    feed = ("<?xml version=\"1.0\"?><rss><channel><item><title>Python Dev at R&D Labs</title><link>https://x.example/1</link><guid>1</guid>"
            "<enclosure url=\"https://a.example/i.png?s=200&v=4\" type=\"image/png\" length=\"0\"/>"
            "<description>Tom &amp; Jerry \x0b and AT&T</description></item></channel></rss>")
    out = adapter(rwfa.RealWorkFromAnywhere, lambda r: httpx.Response(200, text=feed), db).fetch(SearchParams())
    assert out[0].company_name == "R&D Labs" and "AT&T" in out[0].description and "Tom & Jerry" in out[0].description


def test_repair_does_not_weaken_the_entity_protection(db):
    from app.adapters import rwfa
    bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel><item><title>&b;</title>'
            '<link>https://x.example/1</link></item></channel></rss>')
    with pytest.raises(AdapterError):
        adapter(rwfa.RealWorkFromAnywhere, lambda r: httpx.Response(200, text=bomb), db).fetch(SearchParams())


def test_double_encoded_entities_are_decoded_for_every_source(db):
    from app.models import ResearchRun
    run = ResearchRun(params={}); db.add(run); db.commit()
    p = SearchParams(min_fit=0, remote_only=False, posted_within_days=None)
    pipeline.process(db, [raw(1, title="Full Stack Engineer (Angular &amp; Python)", company_name="Tom &#038; Jerry &amp; Co", location_requirements="Europe &amp; Africa")], p, run.id)
    from app.models import Opportunity
    o = db.scalar(select(Opportunity))
    assert o.title == "Full Stack Engineer (Angular & Python)" and o.company_name == "Tom & Jerry & Co" and o.location_requirements == "Europe & Africa"


def test_text_extraction_keeps_a_final_bare_ampersand():
    from app.textutil import html_to_text
    assert html_to_text("AT&T") == "AT&T" and html_to_text("Tom & Jerry and AT&T") == "Tom & Jerry and AT&T"


def test_jobicy_skips_too_short_tags_and_survives_one_rejected_keyword(db):
    asked = []
    def h(req):
        tag = req.url.params["tag"]
        asked.append(tag)
        if tag == "badword":
            return httpx.Response(400, json={"success": False, "error": "The length of the 'tag' value should be between 3 and 50 characters."})
        return httpx.Response(200, json=JOBICY)
    out = adapter(jobicy.Jobicy, h, db).fetch(SearchParams(keywords=["ai", "ml", "badword", "python"]))
    assert asked == ["badword", "python"]                       # "ai" and "ml" are never sent
    assert len(out) == 3                                         # the rejected keyword did not fail the source


def test_jobicy_fails_only_when_every_keyword_is_rejected(db):
    h = lambda req: httpx.Response(400, json={"success": False, "error": "bad tag"})
    with pytest.raises(AdapterError, match="rejected every"):
        adapter(jobicy.Jobicy, h, db).fetch(SearchParams(keywords=["abc", "def"]))
    with pytest.raises(AdapterError):                           # a server error is still a real failure
        adapter(jobicy.Jobicy, lambda r: httpx.Response(503), db).fetch(SearchParams(keywords=["python"]))


# ---------------------------------------------------------------- restrictions stated in the text (real Hacker News wording)
@pytest.mark.parametrize("text,expected", [
    ("Software Engineer — Remote — US Only Kaveronix is looking for experienced engineers", "restricted"),
    ("Remote (U.S. Eastern/Central Time) | Senior Full Stack Python", "restricted"),
    ("Opaxa | Founding Engineer | US work authorization required. No agencies.", "restricted"),
    ("Candidates must be located in the United States and authorized to work in the US", "restricted"),
    ("UK only. Python and AWS.", "restricted"),
    ("Remote worldwide. We hire contractors anywhere, no visa sponsorship offered.", "unknown"),
    ("Acme | Python AI | REMOTE | We love US companies and the US market", "unknown"),
    ("Fully remote, work from anywhere. Python, FastAPI, AWS.", "unknown"),
])
def test_text_restrictions_are_found_when_no_location_is_stated(text, expected):
    from app.scoring import effective_geo
    assert effective_geo("", text) == expected, text


def test_a_stated_location_always_wins_over_the_text():
    from app.scoring import effective_geo
    assert effective_geo("Worldwide", "US only") == "worldwide"            # the structured field is authoritative
    assert effective_geo("UK", "work from anywhere") == "restricted"


def test_us_only_posts_without_a_location_field_are_dropped_by_the_country_filter_and_flagged_in_the_export(db):
    p = SearchParams(country="Tunisia", remote_only=False, posted_within_days=None)
    us = raw(1, location_requirements="", description="Software Engineer — Remote — US Only. Python FastAPI LLM AWS Docker. " * 3)
    ok = raw(2, location_requirements="", description="Remote. Python FastAPI LLM AWS Docker. To apply, email jobs@acme.example " * 3)
    assert not pipeline.passes_filters(us, p)[0] and pipeline.passes_filters(ok, p)[0]
    from .test_csv_and_runs import go
    from .helpers import FakeAdapter
    from app.services import exporter
    go(db, {"fake": FakeAdapter([us, ok])})
    rows = {r["company_name"]: r for r in exporter.build_combined(db)["opportunities"]}
    assert rows["Acme 1"]["location_check"] == "restricted" and rows["Acme 2"]["location_check"] == "unknown"
    leads = exporter.build_combined(db)["leads"]
    assert [l["company_name"] for l in leads] == ["Acme 2"]


def test_in_person_hn_posts_are_not_remote(db):
    import httpx
    from app.adapters import hn_hiring
    def h(req):
        if "author_whoishiring" in str(req.url):
            return httpx.Response(200, json={"hits": [{"objectID": "100", "title": "Ask HN: Who is hiring? (October 2026)"}]})
        return httpx.Response(200, json={"hits": [
            {"objectID": "1", "parent_id": 100, "comment_text": "VLM Run ( https://vlm.run ) | 1x Founding Infrastructure Engineer | In-Person (Bay Area) | Full-time<p>Python AWS"},
            {"objectID": "2", "parent_id": 100, "comment_text": "Acme | Python | Remote | Contract<p>Python AWS"}]})
    out = {o.external_id: o for o in hn_hiring.HNHiring(db, httpx.Client(transport=httpx.MockTransport(h))).fetch(SearchParams())}
    assert out["1"].remote_status == "onsite" and out["2"].remote_status == "remote"


# ---------------------------------------------------------------- "Remote (UK)" and role-title segments (real Hacker News headers)
@pytest.mark.parametrize("loc,expected", [
    ("REMOTE (UK)", "restricted"), ("Remote in Poland", "restricted"), ("Remote (Germany)", "restricted"), ("Remote, Spain", "restricted"),
    ("Remote Europe", "compatible"), ("Remote (EMEA)", "compatible"), ("Remote (Tunisia)", "compatible"), ("Remote", "unknown"),
    ("Remote worldwide", "worldwide"), ("Hybrid London", "restricted"),   # hybrid needs presence in London
])
def test_remote_with_a_country_is_a_restriction(loc, expected):
    from app.scoring import geo_status
    assert geo_status(loc) == expected, loc


def test_hn_location_never_picks_a_job_title_segment(db):
    import httpx
    from app.adapters import hn_hiring
    def h(req):
        if "author_whoishiring" in str(req.url):
            return httpx.Response(200, json={"hits": [{"objectID": "100", "title": "Ask HN: Who is hiring? (October 2026)"}]})
        return httpx.Response(200, json={"hits": [
            {"objectID": "1", "parent_id": 100, "comment_text": "AssumeAI | AI Engineer (£30/hr) and Senior AI Engineer (£50/hr) | Contract | REMOTE (UK) | https://assume-ai.example<p>Python"},
            {"objectID": "2", "parent_id": 100, "comment_text": "Acme | Staff ML Engineer | REMOTE (worldwide) | Full-time<p>Python"},
            {"objectID": "3", "parent_id": 100, "comment_text": "Beta | Backend Developer (SRE focus) | Berlin, DE | Hybrid<p>Python"}]})
    out = {o.external_id: o for o in hn_hiring.HNHiring(db, httpx.Client(transport=httpx.MockTransport(h))).fetch(SearchParams())}
    assert out["1"].location_requirements == "REMOTE (UK)"
    assert out["2"].location_requirements == "REMOTE (worldwide)"
    assert "Engineer" not in out["3"].location_requirements and "Berlin" in out["3"].location_requirements
    from app.scoring import geo_status
    assert geo_status(out["1"].location_requirements) == "restricted" and geo_status(out["2"].location_requirements) == "worldwide"


def test_startup_refreshes_old_hn_rows_to_the_current_location_rules(db):
    from app.models import Opportunity
    from app.services import rescoring
    from .test_csv_and_runs import go
    from .helpers import FakeAdapter
    text = "AssumeAI | AI Engineer (£30/hr) and Senior AI Engineer (£50/hr) | Contract | REMOTE (UK) | https://assume-ai.example\nPython FastAPI LLM AWS Docker. " * 2
    go(db, {"fake": FakeAdapter([raw(1, source_key="hn_hiring", company_name="AssumeAI", description=text, location_requirements="", engagement_type="contract")])})
    o = db.scalar(select(Opportunity))
    o.location_requirements, o.remote_status = "AI Engineer (£30/hr) and Senior AI Engineer (£50/hr); REMOTE (UK)", "unknown"   # what an older version stored
    o.fit_score = 80.0
    db.commit()
    assert rescoring.refresh_hn_locations(db) == 1
    db.refresh(o)
    assert o.location_requirements == "REMOTE (UK)" and o.remote_status == "remote"
    assert rescoring.refresh_hn_locations(db) == 0                                 # stable
    rescoring.rescore_all(db)
    db.refresh(o)
    assert o.fit_score <= 50                                                       # a UK-only role is now capped
    assert rescoring.rescore_all(db) >= 1
