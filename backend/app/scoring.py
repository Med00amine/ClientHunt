"""Transparent 0-100 fit heuristic.

Components (max): skills 35, portfolio relevance 25, budget 15, information quality 10,
remote/schedule 10, freshness 5. Missing data earns 0 for that component and is listed as unknown.
This prioritises what to read first; it does not predict winning a contract.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .portfolio import load_portfolio
from .skills import MY_SKILLS, extract_skills
from .types import RawOpportunity

CORE = {"python", "llm", "rag", "aws", "fastapi", "machine learning", "pytorch", "api integration",
        "workflow automation", "document processing"}
HEAVY_MISMATCH = {"java", "php", "c#/.net", "ruby", "go", "rust", "c++", "mobile", "sap/salesforce"}
RESTRICTED_CAP = 50.0
NON_ENG_CAP = 30.0
_NON_ENG = re.compile(r"\b(sales|business development|bd manager|marketing|go-to-market|gtm|account executive|account manager|"
                      r"recruiter|designer|copywriter|customer success|support specialist|accountant|finance manager|"
                      r"hr manager|operations manager|product manager|project manager|community manager)\b", re.I)
_ENG = re.compile(r"\b(engineer|engineers|developer|developers|programmer|architect|devops|sre|scientist|software|"
                  r"full[- ]?stack|back[- ]?end|front[- ]?end|ml|ai|llm|data|cto|technical|technologist|consultant)\b", re.I)
MAX = {"skills": 35, "portfolio": 25, "budget": 15, "info": 10, "remote": 10, "freshness": 5}

_WORLDWIDE = re.compile(r"worldwide|anywhere|global|any\s+location|international|work from anywhere", re.I)
_COMPATIBLE = re.compile(r"emea|africa|tunisia|europe|\beu\b|\bcet\b", re.I)
_RESTRICTED = re.compile(r"\bus(a)?\s*(only|based|residents?|citizens?)|united states|\bu\.s\.|\bus\b|canada|north america|"
                         r"\b(eastern|pacific|central|mountain)\b.*\b(time|tz)\b|\b(est|pst|cst|edt|pdt)\b|"
                         r"americas|\buk\s+only|australia|\bapac\b|must\s+(live|reside|be located)", re.I)


def now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def geo_status(location: str) -> str:
    """worldwide | compatible | restricted | unknown"""
    loc = (location or "").strip()
    if not loc:
        return "unknown"
    if _WORLDWIDE.search(loc):
        return "worldwide"
    if loc.lower().startswith("time zones:"):  # Tunisia is UTC+1 (no DST)
        return "compatible" if re.search(r"UTC\+1(?!\d|\.)", loc) else "restricted"
    if re.match(r"only:", loc, re.I) and not re.search(r"tunisia|africa|egypt|morocco|algeria", loc, re.I):
        return "restricted"  # explicit country allow-list that does not include Tunisia/Africa
    if _RESTRICTED.search(loc) and not _COMPATIBLE.search(loc):
        return "restricted"
    if _COMPATIBLE.search(loc):
        return "compatible"
    return "unknown"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


SCORED_CURRENCIES = {"USD", "EUR", "GBP", ""}  # no exchange rates are invented: other currencies are not scored


def _hourly_equiv(op: RawOpportunity) -> float | None:
    if (op.currency or "").upper() not in SCORED_CURRENCIES:
        return None
    r = op.budget_max if op.budget_max is not None else op.budget_min
    if r is None:
        return None
    t = op.rate_type
    if t == "hourly":
        return r
    if t == "annual":
        return r / 1800.0
    if t == "monthly":
        return r / 160.0
    return None


def score(op: RawOpportunity, required: list[str] | None = None, portfolio: list[dict] | None = None,
          now: datetime | None = None) -> dict:
    now = now or now_naive()
    portfolio = portfolio if portfolio is not None else load_portfolio()
    detected = extract_skills(op.title, op.description, " ".join(op.tags))
    title_skills = set(extract_skills(op.title))
    mine = [s for s in detected if s in MY_SKILLS]
    other = [s for s in detected if s not in MY_SKILLS]
    unknown: list[str] = []
    notes: list[str] = []

    # --- skills (35)
    weight = sum(1.0 if s in CORE else 0.5 for s in mine) + 0.5 * len([s for s in mine if s in title_skills])
    skills_pts = 35 * _clamp(weight / 3.5)
    heavy_title = [s for s in title_skills if s in HEAVY_MISMATCH]
    heavy_body = [s for s in other if s in HEAVY_MISMATCH and s not in heavy_title]
    if heavy_title:
        skills_pts *= 0.4
        notes.append(f"title centres on skills outside your profile ({', '.join(heavy_title)})")
    elif heavy_body:
        skills_pts *= max(0.6, 1 - 0.15 * len(heavy_body))
    if not detected:
        unknown.append("no recognisable skills in the listing")
    notes.insert(0, f"{len(mine)} of your skills detected ({', '.join(mine) or 'none'})")

    # --- portfolio relevance (25): only verified items earn points
    ev, overlaps = [], []
    for item in portfolio:
        inter = sorted(set(item.get("skills", [])) & set(detected))
        if not inter:
            continue
        ev.append({"id": item["id"], "title": item["title"], "url": item.get("url", ""),
                   "verified": bool(item.get("verified")), "overlap": inter, "summary": item.get("summary", "")})
        if item.get("verified"):
            overlaps.append(len(inter))
    overlaps.sort(reverse=True)
    portfolio_pts = 25 * _clamp(sum(overlaps[:2]) / 7.0)
    ev.sort(key=lambda e: (not e["verified"], -len(e["overlap"])))
    if any(not e["verified"] for e in ev):
        notes.append("some matching portfolio items are unverified and earn no points")
    if not overlaps:
        notes.append("no verified portfolio item overlaps this listing")

    # --- budget (15)
    budget_pts = 0.0
    h = _hourly_equiv(op)
    if h is not None:
        budget_pts = 15 * _clamp((h - 15) / 30.0)
        notes.append(f"≈{h:.0f} {op.currency or ''}/h equivalent")
    elif (op.currency or "").upper() not in SCORED_CURRENCIES and (op.budget_max is not None or op.budget_min is not None):
        unknown.append(f"budget in {op.currency} not converted/scored")
    elif op.budget_max is not None or op.budget_min is not None:
        r = op.budget_max if op.budget_max is not None else op.budget_min
        budget_pts = 15 * _clamp((r - 200) / 2300.0)
    else:
        unknown.append("budget/rate not published")

    # --- information quality (10)
    info_pts = 0.0
    info_pts += 3 if op.company_name else 0
    info_pts += 3 if op.company_website else 0
    info_pts += 2 if len(op.description or "") > 300 else 0
    info_pts += 1 if op.url else 0
    info_pts += 1 if op.posted_at else 0
    if not op.company_name:
        unknown.append("client/company not named")

    # --- remote & schedule (10)
    remote_pts = 0.0
    geo = geo_status(op.location_requirements)
    if op.remote_status == "remote":
        remote_pts += 6
    elif op.remote_status == "unknown":
        unknown.append("remote status unknown")
    if geo == "worldwide":
        remote_pts += 4
    elif geo == "compatible":
        remote_pts += 3
        notes.append("location text suggests Europe/Africa-compatible; confirm you are eligible from Tunisia")
    elif geo == "restricted":
        notes.append(f"location restriction may exclude you: {op.location_requirements[:80]}")
    else:
        unknown.append("location/time-zone requirement unknown")

    # --- freshness (5)
    fresh_pts = 0.0
    if op.posted_at:
        age = (now - op.posted_at).days
        fresh_pts = 5 if age <= 3 else 4 if age <= 7 else 3 if age <= 14 else 1 if age <= 30 else 0
    else:
        unknown.append("posting date unknown")

    comps = {"skills": skills_pts, "portfolio": portfolio_pts, "budget": budget_pts,
             "info": info_pts, "remote": remote_pts, "freshness": fresh_pts}
    comps = {k: round(v, 1) for k, v in comps.items()}
    total = round(min(100.0, sum(comps.values())), 1)
    if _NON_ENG.search(op.title) and not _ENG.search(op.title) and total > NON_ENG_CAP:
        notes.append(f"score capped at {NON_ENG_CAP:.0f}: the title looks like a non-engineering role")
        total = NON_ENG_CAP
    if geo == "restricted" and total > RESTRICTED_CAP:
        notes.append(f"score capped at {RESTRICTED_CAP} because a location restriction may exclude you")
        total = RESTRICTED_CAP

    missing = [f"{s} (listing asks, not in your profile)" for s in other]
    for r in required or []:
        if r.lower() not in {d.lower() for d in detected}:
            missing.append(f"{r} (requested in search, not found in listing)")
    if geo == "restricted":
        missing.append("location/eligibility restriction")

    known = sum(MAX[k] for k, v in {"budget": h is not None or op.budget_max is not None or op.budget_min is not None,
                                     "remote": op.remote_status != "unknown", "freshness": bool(op.posted_at),
                                     "info": True, "skills": bool(detected), "portfolio": True}.items() if v)
    explanation = "; ".join(notes)
    if unknown:
        explanation += ". Unknown (scored 0): " + ", ".join(unknown)
    return {
        "total": total, "components": comps, "max": MAX, "explanation": explanation,
        "detected_skills": detected, "matched_skills": mine, "missing": missing,
        "portfolio_evidence": ev, "unknown": unknown, "geo": geo,
        "data_coverage": round(known / 100, 2),
    }


def recommend(op_status: str, total: float, geo: str, has_verified_evidence: bool) -> str:
    if op_status == "closed":
        return "Skip: listing closed"
    if geo == "restricted":
        return "Check location eligibility before spending time"
    if total >= 60:
        return "High priority: review, research the client, draft a proposal"
    if total >= 40:
        return "Worth a look: read the full listing" + ("" if has_verified_evidence else " (no verified portfolio match)")
    return "Low priority: only if nothing better"
