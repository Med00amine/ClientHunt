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
_NON_ENG = re.compile(r"\b(sales|business development|bd manager|marketing|marketer|go-to-market|gtm|account executive|account manager|"
                      r"recruiter|designer|creative|copywriter|writer|editor|translator|interpreter|artist|customer success|"
                      r"customer support|support specialist|accountant|finance manager|hr manager|operations manager|"
                      r"product manager|project manager|community manager|nurse|annotation|annotator|trainer|tutor|teacher)\b", re.I)
# Role words only. Topics such as "AI", "ML" or "data" are NOT role words: "AI Lead Creative" is not an engineering job.
_ENG = re.compile(r"\b(engineer|engineers|engineering|developer|developers|programmer|architect|devops|sre|scientist|researcher|software|"
                  r"full[- ]?stack|back[- ]?end|front[- ]?end|cto|technologist)\b", re.I)
MAX = {"skills": 35, "portfolio": 25, "budget": 15, "info": 10, "remote": 10, "freshness": 5}

_WORLDWIDE = re.compile(r"worldwide|anywhere|global|any\s+location|international|work from anywhere", re.I)
_COMPATIBLE = re.compile(r"emea|africa|tunisia|egypt|morocco|algeria|libya|nigeria|kenya|ghana|senegal|europe|\beu\b|\bcet\b", re.I)
_ALLOW_REGIONS = {"tunisia", "africa", "north africa", "emea", "mena", "europe", "eu", "worldwide", "anywhere", "global"}
_RESTRICTED = re.compile(r"\bus(a)?\s*(only|based|residents?|citizens?)|united states|\bu\.s\.|\bus\b|canada|north america|"
                         r"\b(eastern|pacific|central|mountain)\b.*\b(time|tz)\b|\b(est|pst|cst|edt|pdt)\b|"
                         r"americas|\buk\s+only|australia|\bapac\b|must\s+(live|reside|be located)", re.I)


def now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_COUNTRIES = {n.strip() for n in """usa, us, united states, america, uk, united kingdom, england, scotland, wales, britain, ireland, canada, mexico,
brazil, argentina, chile, colombia, peru, uruguay, paraguay, bolivia, venezuela, ecuador, costa rica, panama, guatemala, germany, france,
spain, italy, portugal, netherlands, belgium, luxembourg, switzerland, austria, sweden, norway, denmark, finland, iceland, poland, czechia,
czech republic, slovakia, hungary, romania, bulgaria, greece, croatia, serbia, slovenia, lithuania, latvia, estonia, ukraine, belarus,
russia, turkey, cyprus, malta, georgia, armenia, israel, india, pakistan, bangladesh, sri lanka, nepal, china, japan, korea, south korea,
taiwan, hong kong, singapore, malaysia, indonesia, philippines, vietnam, thailand, australia, new zealand, latam, latin america, americas,
north america, south america, apac, asia, asia pacific, oceania, saudi arabia, uae, united arab emirates, qatar, kuwait""".split(",")}
_COUNTRY_PHRASES = ("united states", "united kingdom", "czech republic", "costa rica", "south korea", "hong kong", "new zealand",
                    "latin america", "north america", "south america", "asia pacific", "saudi arabia", "united arab emirates", "sri lanka")
_COMPAT_TOKENS = {"emea", "africa", "tunisia", "egypt", "morocco", "algeria", "nigeria", "kenya", "ghana", "europe", "eu", "cet", "worldwide",
                  "anywhere", "global", "international"}


def _only_countries(loc: str) -> bool:
    """True when the text is just a list of countries/regions (e.g. "UK", "Canada, USA", "LATAM, Argentina") and
    names none that includes Tunisia (Africa/EMEA/Europe/worldwide). That is a residency restriction."""
    text = " " + re.sub(r"[()]", " ", loc.lower()) + " "
    text = re.sub(r"\b(remote|remotely|only|based|in|within|from|across|for|hybrid)\b", " ", text)   # "Remote (UK)" -> "uk"
    for ph in _COUNTRY_PHRASES:
        text = text.replace(ph, ph.replace(" ", "_"))
    parts = [p.strip().replace("_", " ") for p in re.split(r"[,;/|&]| and | or ", text) if p.strip()]
    if not parts:
        return False
    words = [w for p in parts for w in ([p] if p in _COUNTRIES else p.split())]
    if any(w in _COMPAT_TOKENS for w in words):
        return False
    return all(p in _COUNTRIES for p in parts)


# Residency statements in the listing TEXT. A structured location field is often generic ("Worldwide") while the text says
# "Location: LATAM 100% Remote" or "must be located in the US", so these STRONG statements override a field that is not restricted.
_REGION = (r"latam|latin america|north america|(?:the )?(?:us|u\.s\.|usa|united states)|uk|canada|brazil|mexico|argentina|colombia|chile|peru")
_TEXT_STRONG = re.compile(
    r"\b(must|need to|should) (be (located|based|living|resident)|reside|live) in (the )?(us|u\.s\.|usa|united states|uk|united kingdom|eu|canada)\b|"
    r"\bauthori[sz]ed to work in (the )?(us|u\.s\.|usa|united states|uk|united kingdom|eu|canada)\b|"
    r"\b(us|u\.s\.|uk|eu) work authori[sz]ation (is )?required\b|"
    # "Location: LATAM 100% Remote", "Location: USA & LATAM | Remote" (but not "Location: UK / Europe" or "Location: US or EMEA")
    r"\blocation\s*:\s*(" + _REGION + r")\b(?!\s*(,|/|&|and|or)\s*(europe|emea|africa|worldwide|anywhere|tunisia))", re.I)
# Looser wording, trusted only when the location field says nothing ("US only benefits" must not hide a worldwide role).
_TEXT_RESTRICTION = re.compile(
    r"\b(us|u\.s\.|usa|united states|uk|u\.k\.|eu|canada)[ -]?(only|based candidates|residents only|citizens only)\b|"
    r"\b(us|u\.s\.|uk|eu) work authori[sz]ation (is )?required\b|\bremote \((us|u\.s\.|usa)[ /,)]", re.I)


def effective_geo(location: str, description: str = "") -> str:
    """geo_status(location), corrected by what the listing text says: a strong residency statement makes a listing
    restricted whatever the field says, and looser wording does so only when the location is not stated."""
    g = geo_status(location)
    if g != "restricted" and description:
        head = description[:3500]
        if _TEXT_STRONG.search(head) or (g == "unknown" and _TEXT_RESTRICTION.search(head)):
            return "restricted"
    return g


def geo_status(location: str) -> str:
    """worldwide | compatible | restricted | unknown"""
    loc = (location or "").strip()
    if not loc:
        return "unknown"
    if re.match(r"\s*(on[- ]?site|in[- ]person|hybrid)\b", loc, re.I):
        return "restricted"      # a physical presence somewhere else is required (a role that says "Remote or onsite ..." starts with Remote)
    if _WORLDWIDE.search(loc):
        return "worldwide"
    if loc.lower().startswith("time zones:"):  # Tunisia is UTC+1 (no DST)
        return "compatible" if re.search(r"UTC\+1(?!\d|\.)", loc) else "restricted"
    m = re.match(r"only:\s*([^;]*)", loc, re.I)
    if m:  # an explicit residency allow-list: it includes Tunisia only if it names Tunisia or a region that contains it
        items = {i.strip().lower() for i in m.group(1).split(",") if i.strip()}
        return "compatible" if items & _ALLOW_REGIONS else "restricted"   # "South Africa" or "Egypt" alone do not include Tunisia
    if _RESTRICTED.search(loc) and not _COMPATIBLE.search(loc):
        return "restricted"
    if _COMPATIBLE.search(loc):
        return "compatible"
    if _only_countries(loc):
        return "restricted"
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
    geo = effective_geo(op.location_requirements, op.description)
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
