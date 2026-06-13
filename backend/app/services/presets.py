"""Sources and the five saved search profiles (seeded idempotently)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SearchProfile, Source

CHECKED = "2026-10-26"
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
    dict(key="hn_hiring", name="Hacker News: Who is hiring?", kind="api", enabled=True, verified=False,
         docs_url="https://hn.algolia.com/api", terms_url="https://hn.algolia.com/api",
         notes="Algolia HN API, no key. Exact rate limit not verified. Comments are untrusted free text."),
    dict(key="upwork", name="Upwork (official API)", kind="unavailable", enabled=False, verified=True,
         docs_url="https://support.upwork.com/hc/en-us/articles/115015857647-How-to-request-an-API-key-from-Upwork",
         terms_url="https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly",
         notes="API needs approval (reported $25k/JSS 90% thresholds, non-commercial). Scraping prohibited. Use saved-search email alerts via Alert import."),
    dict(key="freelancer", name="Freelancer.com (official API)", kind="unavailable", enabled=False, verified=False,
         docs_url="https://developers.freelancer.com", terms_url="",
         notes="Official docs could not be verified; needs OAuth token. Not implemented."),
    dict(key="alerts", name="Job-alert emails (Upwork, Contra, PeoplePerHour, Guru, Wellfound...)", kind="alert", enabled=True,
         verified=True, notes="Paste or upload alert emails; parsed locally. You apply on the platform yourself."),
    dict(key="manual", name="Manual entry", kind="manual", enabled=True, verified=True,
         notes="Add a listing or an agency page you found yourself, with its URL."),
]

COMMON = dict(remote_only=True, posted_within_days=30, max_results=100, max_budget_usd=1.0, min_fit=20.0,
              engagement_types=["contract", "freelance", "part_time"],
              sources=["remotive", "remoteok", "himalayas", "hn_hiring"])
PROFILES = {
    "AI/LLM and RAG projects": dict(keywords=["llm", "rag", "retrieval", "generative ai", "openai"],
                                    required_skills=["llm", "python"]),
    "Python and FastAPI projects": dict(keywords=["python", "fastapi"], required_skills=["python", "fastapi"]),
    "AWS and cloud deployment projects": dict(keywords=["aws", "docker", "devops"], required_skills=["aws", "docker"]),
    "Workflow automation and API integration": dict(keywords=["automation", "integration", "api"],
                                                    required_skills=["api integration", "workflow automation"]),
    "Agency subcontracting and remote B2B contracts": dict(keywords=["contractor", "subcontract", "agency", "freelance"],
                                                           required_skills=["python"]),
    "Easy to reach: hiring now, apply by email": dict(
        keywords=["python", "fastapi", "llm", "ai", "machine learning", "aws", "api", "automation"],
        required_skills=["python"], require_email=True, min_fit=35.0, max_results=150, sources=["hn_hiring"]),
}


def seed(db: Session) -> None:
    for s in SOURCES:
        row = db.scalar(select(Source).where(Source.key == s["key"]))
        if not row:
            db.add(Source(checked_at=CHECKED, **s))
    for name, p in PROFILES.items():
        row = db.scalar(select(SearchProfile).where(SearchProfile.name == name))
        if not row:
            db.add(SearchProfile(name=name, params={**COMMON, **p}, is_preset=True))
        elif row.is_preset and row.params != {**COMMON, **p}:
            row.params = {**COMMON, **p}  # presets are managed by the app and follow code updates
    db.commit()
