"""Sources and the five saved search profiles (seeded idempotently)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SearchProfile, Source

CHECKED = "2026-10-27"
SOURCES = [
    dict(key="remotive", name="Remotive (public API)", kind="api", enabled=True, verified=True,
         docs_url="https://github.com/remotive-com/remote-jobs-api", terms_url="https://github.com/remotive-com/remote-jobs-api",
         notes="No key. Max ~4 fetches/day (cached 6h), 24h delay, must link back and credit Remotive; do not collect emails."),
    dict(key="remoteok", name="Remote OK (public API)", kind="api", enabled=True, verified=True,
         docs_url="https://remoteok.com/api", terms_url="https://remoteok.com/api",
         notes="No key. Terms notice in first element: link back (followed link) and credit Remote OK."),
    dict(key="himalayas", name="Himalayas (public API)", kind="api", enabled=True, verified=True,
         docs_url="https://himalayas.app/api", terms_url="https://himalayas.app/api",
         notes="No key (free key raises limits). Use applicationLink unchanged, link to Himalayas, show only in your own app."),
    dict(key="jobicy", name="Jobicy (public API)", kind="api", enabled=True, verified=True,
         docs_url="https://jobicy.com/jobs-rss-feed", terms_url="https://jobicy.com/jobs-rss-feed",
         notes="No key. Credit Jobicy and link to its listing (done). Storing/caching allowed. Polled at most hourly; covers the last 7 days. Includes real Contract/Freelance listings."),
    dict(key="wwr", name="We Work Remotely (RSS)", kind="api", enabled=True, verified=False,
         docs_url="https://weworkremotely.com/remote-job-rss-feed", terms_url="",
         notes="Public RSS feeds offered by the site (robots.txt allows). Its terms page blocked automated reading (HTTP 403), so terms are not verified: polled every 6 h, every listing links back. Has A.Team and other independent-contractor roles."),
    dict(key="rwfa", name="Real Work From Anywhere (RSS)", kind="api", enabled=True, verified=False,
         docs_url="https://www.realworkfromanywhere.com", terms_url="",
         notes="RSS feed advertised on the site (robots.txt allows); no terms page exists, so terms are not verified: polled every 6 h. Every role is work-from-anywhere (open to Tunisia)."),
    dict(key="pythonorg", name="Python Job Board (RSS)", kind="api", enabled=True, verified=False,
         docs_url="https://www.python.org/jobs/", terms_url="",
         notes="The board's own RSS feed (robots.txt allows). Legal pages could not be read, so terms are not verified: polled every 6 h. Items have no posting date."),
    dict(key="hn_hiring", name="Hacker News: Who is hiring?", kind="api", enabled=True, verified=False,
         docs_url="https://hn.algolia.com/api", terms_url="https://hn.algolia.com/api",
         notes="Algolia HN API, no key. Exact rate limit not verified. Comments are untrusted free text. Many posts publish an application email."),
    dict(key="freelancer_live", name="Freelancer.com: live projects (not stored)", kind="live", enabled=True, verified=True,
         docs_url="https://developers.freelancer.com", terms_url="https://www.freelancer.com/about/apiterms",
         notes="Public API, no login. Its API terms say 'You may not copy or store any Data' (caching only, refreshed within 24 h), so projects are shown live on the Live projects tab and are never saved, exported or added to runs. Bid on Freelancer.com yourself."),
    dict(key="upwork", name="Upwork (official API)", kind="unavailable", enabled=False, verified=True,
         docs_url="https://support.upwork.com/hc/en-us/articles/115015857647-How-to-request-an-API-key-from-Upwork",
         terms_url="https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly",
         notes="API needs approval (reported $25k/JSS 90% thresholds, non-commercial). Scraping prohibited. Use saved-search email alerts via Alert import."),
    dict(key="freelancer", name="Freelancer.com (stored in runs)", kind="unavailable", enabled=False, verified=True,
         docs_url="https://developers.freelancer.com", terms_url="https://www.freelancer.com/about/apiterms",
         notes="Not part of runs or exports: the API terms forbid storing its data. Use the Live projects tab."),
    dict(key="alerts", name="Job-alert emails (Upwork, Contra, PeoplePerHour, Guru, Wellfound...)", kind="alert", enabled=True,
         verified=True, notes="Paste or upload alert emails; parsed locally. You apply on the platform yourself."),
    dict(key="manual", name="Manual entry", kind="manual", enabled=True, verified=True,
         notes="Add a listing or an agency page you found yourself, with its URL."),
]

COMMON = dict(remote_only=True, country="Tunisia", posted_within_days=30, max_results=100, max_budget_usd=1.0, min_fit=20.0,
              engagement_types=["contract", "freelance", "part_time"],
              sources=["remotive", "remoteok", "himalayas", "jobicy", "wwr", "pythonorg", "rwfa", "hn_hiring"])
PROFILES = {
    "AI/LLM and RAG projects": dict(keywords=["llm", "rag", "retrieval", "generative ai", "openai"],
                                    required_skills=["llm", "python"]),
    "Python and FastAPI projects": dict(keywords=["python", "fastapi"], required_skills=["python", "fastapi"]),
    "AWS and cloud deployment projects": dict(keywords=["aws", "docker", "devops"], required_skills=["aws", "docker"]),
    "Workflow automation and API integration": dict(keywords=["automation", "integration", "api"],
                                                    required_skills=["api integration", "workflow automation"]),
    "Agency subcontracting and remote B2B contracts": dict(keywords=["contractor", "subcontract", "agency", "freelance"],
                                                           required_skills=["python"]),
    "AI / ML projects: contract & freelance only": dict(
        keywords=["machine learning", "llm", "rag", "generative ai", "ai engineer", "nlp", "pytorch", "computer vision",
                  "data scientist", "mlops", "langchain", "openai"],
        required_skills=[], min_fit=35.0, strict_engagement=True, max_results=150),
    "Easy to reach: hiring now, apply by email": dict(
        keywords=["python", "fastapi", "llm", "ai", "machine learning", "aws", "api", "automation"],
        required_skills=["python"], require_email=True, min_fit=35.0, max_results=150),
}


def seed(db: Session) -> None:
    for s in SOURCES:
        row = db.scalar(select(Source).where(Source.key == s["key"]))
        if not row:
            db.add(Source(checked_at=CHECKED, **s))
        else:  # sources are managed by the app: follow code updates, but keep the user's enabled/disabled choice
            for k, v in s.items():
                if k != "enabled":
                    setattr(row, k, v)
            row.checked_at = CHECKED
    for name, p in PROFILES.items():
        row = db.scalar(select(SearchProfile).where(SearchProfile.name == name))
        if not row:
            db.add(SearchProfile(name=name, params={**COMMON, **p}, is_preset=True))
        elif row.is_preset and row.params != {**COMMON, **p}:
            row.params = {**COMMON, **p}  # presets are managed by the app and follow code updates
    db.commit()
