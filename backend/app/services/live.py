"""Live view of open Freelancer.com projects.

Freelancer.com's API terms (https://www.freelancer.com/about/apiterms, section 5) say "You may not copy or store any
Data" and only allow caching for performance, refreshed at least every 24 hours. So this module NEVER writes
anything to the database, to exports or to disk: results live in a short in-memory cache (15 minutes) and are shown
to the signed-in user. Bidding is done by the user on Freelancer.com."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import httpx

from ..config import get_settings
from ..scoring import score
from ..textutil import html_to_text
from ..types import RawOpportunity

CACHE_SECONDS = 15 * 60                # well inside the 24 h the terms allow
DEFAULT_QUERIES = ["machine learning", "LLM", "RAG chatbot", "AI agent", "NLP", "computer vision", "python AI", "data science"]
MAX_QUERIES = 6
PROJECT_URL = "https://www.freelancer.com/projects/"

_cache: dict[tuple, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


class LiveSourceError(Exception):
    pass


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _raw(p: dict) -> list[dict]:
    return p.get("result", {}).get("projects", []) if isinstance(p, dict) else []


def _fetch_query(client: httpx.Client, query: str, limit: int, now: float) -> list[dict]:
    key = (query.lower(), limit)
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        r = client.get(get_settings().freelancer_api_url, params={
            "query": query, "limit": str(limit), "job_details": "true", "full_description": "true", "compact": "false"},
            headers={"User-Agent": get_settings().http_user_agent})
    except httpx.TransportError as e:
        raise LiveSourceError(f"Could not reach Freelancer.com: {type(e).__name__}") from e
    if r.status_code == 429:
        raise LiveSourceError("Freelancer.com asked us to slow down. Try again in a few minutes.")
    if r.status_code >= 400:
        raise LiveSourceError(f"Freelancer.com answered HTTP {r.status_code}")
    try:
        projects = _raw(r.json())
    except ValueError as e:
        raise LiveSourceError("Freelancer.com returned an unreadable response") from e
    with _lock:
        _cache[key] = (now, projects)
    return projects


def _shape(p: dict, now_dt: datetime) -> dict | None:
    if p.get("status") != "active" or p.get("frontend_project_status") not in (None, "open") or p.get("nonpublic") or p.get("deleted"):
        return None
    cur = p.get("currency") or {}
    bud = p.get("budget") or {}
    lo, hi = float(bud.get("minimum") or 0), float(bud.get("maximum") or 0)
    rate = float(cur.get("exchange_rate") or 0)
    posted = datetime.fromtimestamp(int(p.get("time_submitted") or 0), timezone.utc).replace(tzinfo=None) if p.get("time_submitted") else None
    bids = int((p.get("bid_stats") or {}).get("bid_count") or 0)
    text = html_to_text(p.get("description") or p.get("preview_description") or "", 4000)
    skills = [j.get("name", "") for j in (p.get("jobs") or []) if j.get("name")]
    kind = p.get("type") or ""
    fit = score(RawOpportunity(
        source_key="freelancer_live", url=PROJECT_URL + str(p.get("seo_url", "")), title=p.get("title", ""),
        description=text + "\n" + " ".join(skills), tags=skills, posted_at=posted, engagement_type="freelance",
        remote_status="remote", location_requirements="Worldwide", budget_min=lo or None, budget_max=hi or None,
        currency=cur.get("code", ""), rate_type="hourly" if kind == "hourly" else "fixed" if kind == "fixed" else ""), None)
    age_min = int((now_dt - posted).total_seconds() // 60) if posted else None
    return {
        "id": p.get("id"), "title": p.get("title", ""), "url": PROJECT_URL + str(p.get("seo_url", "")), "type": kind,
        "budget_min": lo, "budget_max": hi, "currency": cur.get("code", ""), "currency_sign": cur.get("sign", ""),
        "budget_max_usd": round(hi * rate, 2) if rate else None, "bids": bids,
        "bid_avg": round(float((p.get("bid_stats") or {}).get("bid_avg") or 0), 2),
        "competition": "few bids" if bids < 10 else "some bids" if bids < 40 else "crowded",
        "posted_at": posted.isoformat() + "Z" if posted else None, "age_minutes": age_min, "skills": skills,
        "excerpt": text[:320], "fit": fit["total"], "matched_skills": fit["matched_skills"],
        "urgent": bool(p.get("urgent")), "language": p.get("language", ""),
        # transparent heuristic: your fit, minus competition, plus a little for freshness (0-100)
        "worth": round(max(0.0, min(100.0, fit["total"] - min(35.0, bids * 0.3)
                                    + (8 if age_min is not None and age_min < 360 else 4 if age_min is not None and age_min < 1440 else 0))), 1),
    }


def search_projects(queries: list[str] | None = None, min_usd: float = 0, max_bids: int = 0, kind: str = "",
                    sort: str = "best", limit: int = 40, client: httpx.Client | None = None,
                    now: float | None = None, min_hourly_usd: float = 0) -> dict:
    """Open projects matching any query, merged and de-duplicated. Nothing is stored."""
    qs = [q.strip() for q in (queries or DEFAULT_QUERIES) if q and q.strip()][:MAX_QUERIES] or DEFAULT_QUERIES[:MAX_QUERIES]
    own = client is None
    client = client or httpx.Client(timeout=20)
    now = time.time() if now is None else now
    now_dt = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    try:
        merged: dict[int, dict] = {}
        for q in qs:
            for p in _fetch_query(client, q, 50, now):
                row = _shape(p, now_dt)
                if row and row["id"] not in merged:
                    merged[row["id"]] = row
    finally:
        if own:
            client.close()
    rows = list(merged.values())
    if kind in ("fixed", "hourly"):
        rows = [r for r in rows if r["type"] == kind]
    if min_usd or min_hourly_usd:   # fixed projects compare the budget, hourly ones compare the hourly rate
        rows = [r for r in rows if (r["budget_max_usd"] or 0) >= (min_hourly_usd if r["type"] == "hourly" else min_usd)]
    if max_bids:
        rows = [r for r in rows if r["bids"] <= max_bids]
    if sort == "newest":
        rows.sort(key=lambda r: r["age_minutes"] if r["age_minutes"] is not None else 10 ** 9)
    elif sort == "fewest_bids":
        rows.sort(key=lambda r: (r["bids"], -r["fit"]))
    else:  # best: highest "worth" (fit - competition + freshness) first
        rows.sort(key=lambda r: (-r["worth"], r["bids"]))
    return {"queries": qs, "total_matches": len(rows), "items": rows[:max(1, min(limit, 100))],
            "cached_for_minutes": CACHE_SECONDS // 60,
            "notice": ("Shown live from Freelancer.com's public API. Its terms do not allow storing its data, so these "
                       "projects are not saved, exported or added to your runs. Bid on Freelancer.com yourself.")}
