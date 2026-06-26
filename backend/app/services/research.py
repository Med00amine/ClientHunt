"""Evidence-based company research. Facts are verbatim excerpts from fetched pages (verified to be
substrings of the page text); hypotheses are stored separately and never used in drafts unless approved."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import Company, Evidence, Opportunity, utcnow
from urllib.parse import urlsplit

from ..textutil import html_to_text
from . import leads
from .safefetch import FetchBlocked, SafeFetcher

TOPICS = {
    "AI / machine learning": r"\b(ai|artificial intelligence|machine learning|llm|generative)\b",
    "Python": r"\bpython\b",
    "AWS / cloud": r"\b(aws|amazon web services|cloud)\b",
    "API / integrations": r"\b(api|apis|integrations?|webhooks?)\b",
    "automation": r"\bautomat(e|ion|ing)\b",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


CONTACT_PATHS = ("/contact", "/contact-us", "/careers", "/jobs", "/join-us")
_SLD = {"co", "com", "org", "net", "ac", "gov", "edu"}


def site_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def discover_emails(db: Session, opp: Opportunity, fetcher: SafeFetcher, home_url: str, pages: list) -> int:
    """Role mailboxes (jobs@, careers@, contact@...) published on the company's own pages, same domain only."""
    domain = site_domain(home_url)
    pages = list(pages)
    have = {u for u, _ in pages}
    for path in CONTACT_PATHS:
        if len(pages) >= 5:
            break
        url = home_url.rstrip("/") + path
        if url in have:
            continue
        try:
            pages.append(fetcher.get_html(url))
        except Exception:  # noqa: BLE001 - optional pages
            continue
    n = 0
    for url, html in pages:
        n += len(leads.attach_emails(db, opp, html_to_text(html, 60000), "website", source_url=url,
                                     only_role_on_domain=domain))
    return n


def research_company(db: Session, company: Company, opp: Opportunity | None, fetcher: SafeFetcher) -> int:
    """Returns number of evidence rows stored. Sets company.research_status."""
    if not company.website:
        company.research_status = "no_website"
        db.commit()
        return 0
    pages = []
    try:
        url, html = fetcher.get_html(company.website)
        pages.append((url, html))
        for path in ("/about", "/about-us"):
            try:
                pages.append(fetcher.get_html(url.rstrip("/") + path))
                break
            except (FetchBlocked, Exception):  # noqa: BLE001 - optional page
                continue
    except Exception as e:  # noqa: BLE001
        company.research_status = "failed"
        company.last_error = str(e)[:300]
        company.researched_at = utcnow()
        db.commit()
        return 0

    db.execute(delete(Evidence).where(Evidence.company_id == company.id, Evidence.approved.is_(False)))
    n = 0
    now = utcnow()
    seen: set[str] = set()        # the same text on several URLs (catch-all sites) is stored once
    mentioned: list[str] = []
    first_url = pages[0][0]
    for page_url, html in pages:
        soup = BeautifulSoup(html, "html.parser")
        raw_text = html_to_text(html, 60000)  # keeps line breaks so headings and paragraphs stay separate excerpts
        text = _norm(raw_text)
        title = _norm(soup.title.get_text()) if soup.title else ""
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        desc = _norm(meta.get("content", "")) if meta else ""
        candidates = []
        if title:
            candidates.append(("Page title", title, "high"))
        if desc:
            candidates.append(("Company describes itself", desc, "high"))
        hits: dict[str, list[str]] = {}   # sentence -> topics it mentions (one fact per sentence)
        for topic, pat in TOPICS.items():
            for sent in re.split(r"(?<=[.!?])\s+|\n", raw_text):
                sent = _norm(sent)
                if sent in (title, desc):
                    continue  # already recorded as the page title / self-description
                if re.search(pat, sent, re.I) and 25 < len(sent) < 300:
                    hits.setdefault(sent, []).append(topic)
                    if topic not in mentioned:
                        mentioned.append(topic)
                    break
        for sent, topics in hits.items():
            candidates.append((f"Site mentions {', '.join(topics)}", sent, "medium"))
        for label, excerpt, conf in candidates:
            hay = text + " " + title + " " + desc
            if excerpt not in hay or excerpt in seen:  # verification: excerpt must really be in the page
                continue
            seen.add(excerpt)
            db.add(Evidence(company_id=company.id, opportunity_id=opp.id if opp else None, kind="fact",
                            claim=f"{label}: {excerpt[:200]}", excerpt=excerpt[:400], source_url=page_url,
                            retrieved_at=now, confidence=conf, approved=False))
            n += 1
            if label == "Company describes itself" and not company.description:
                company.description = excerpt[:600]
    if mentioned and opp is not None:
        db.add(Evidence(company_id=company.id, opportunity_id=opp.id, kind="hypothesis",
                        claim=f"Hypothesis (unverified inference): site mentions {', '.join(mentioned)}, so work on "
                              f"your matching skills may be relevant. Confirm with the client before relying on it.",
                        excerpt="", source_url=first_url, retrieved_at=now, confidence="low", approved=False))
        n += 1
    emails = discover_emails(db, opp, fetcher, pages[0][0], pages) if opp is not None else 0
    company.research_status = "done" if (n or emails) else "no_evidence"
    company.researched_at = now
    company.last_error = ""
    if opp is not None:
        opp.research_status = company.research_status
    db.commit()
    return n
