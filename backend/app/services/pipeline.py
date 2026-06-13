"""Normalise -> filter -> deduplicate -> score -> upsert, with change history."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Company, Opportunity, OpportunityHistory, RunOpportunity, utcnow)
from ..portfolio import load_portfolio
from ..scoring import geo_status, now_naive, recommend, score
from ..textutil import canonical_url, content_hash, fingerprint, norm_text
from ..types import RawOpportunity, SearchParams
from . import leads

ENGAGEMENT_ALIASES = {"contract": {"contract", "freelance"}, "freelance": {"freelance", "contract"},
                      "part_time": {"part_time"}, "full_time": {"full_time"}}


def external_id(raw: RawOpportunity) -> str:
    if raw.external_id:
        return raw.external_id[:300]
    return "url:" + hashlib.sha256(canonical_url(raw.url).encode()).hexdigest()[:32]


def passes_filters(raw: RawOpportunity, p: SearchParams, now=None) -> tuple[bool, str]:
    now = now or now_naive()
    if p.remote_only and raw.remote_status in ("onsite", "hybrid"):
        return False, "not remote"
    if p.engagement_types:
        wanted = set().union(*(ENGAGEMENT_ALIASES.get(t, {t}) for t in p.engagement_types))
        if raw.engagement_type != "unknown" and raw.engagement_type not in wanted:
            return False, f"engagement type {raw.engagement_type}"
    if p.posted_within_days and raw.posted_at and raw.posted_at < now - timedelta(days=p.posted_within_days):
        return False, "older than date range"
    if p.min_rate is not None and raw.rate_type == "hourly" and raw.budget_max is not None and raw.budget_max < p.min_rate:
        return False, "below minimum rate"
    if p.country and geo_status(raw.location_requirements) == "restricted":
        if p.country.lower() not in raw.location_requirements.lower():
            return False, "location restriction"
    kws = [k.lower() for k in (p.keywords + p.required_skills) if k]
    if kws:
        blob = f"{raw.title}\n{raw.description}\n{' '.join(raw.tags)}".lower()
        if not any(k in blob for k in kws):
            return False, "no keyword match"
    return True, ""


def find_existing(db: Session, raw: RawOpportunity, fp: str) -> Opportunity | None:
    ext = external_id(raw)
    row = db.scalar(select(Opportunity).where(Opportunity.source_key == raw.source_key,
                                              Opportunity.external_id == ext))
    if row:
        return row
    cu = canonical_url(raw.url)
    if cu:
        row = db.scalar(select(Opportunity).where(Opportunity.canonical_url == cu))
        if row:
            return row
    # cross-source duplicate: same company + same full title + same description start
    if raw.company_name:
        return db.scalar(select(Opportunity).where(Opportunity.fingerprint == fp))
    return None


def get_or_create_company(db: Session, raw: RawOpportunity) -> Company | None:
    if not raw.company_name:
        return None
    n = norm_text(raw.company_name)
    c = db.scalar(select(Company).where(Company.name_norm == n))
    if not c:
        c = Company(name=raw.company_name[:300], name_norm=n)
        db.add(c)
        db.flush()
    if raw.company_website and not c.website:
        c.website, c.website_source = raw.company_website[:500], raw.company_website_source or "listing_field"
    return c


def process(db: Session, raws: list[RawOpportunity], p: SearchParams, run_id: int,
            portfolio: list[dict] | None = None) -> dict:
    """Returns counters. Never marks anything applied; only stores listings."""
    portfolio = portfolio if portfolio is not None else load_portfolio()
    stats = {"discovered": len(raws), "stored": 0, "new": 0, "rejected_irrelevant": 0,
             "rejected_duplicate": 0, "ids": []}
    seen_in_run: set[int] = set()
    seen_fp: set[str] = set()
    scored = []
    for raw in raws:
        if not raw.url or not raw.title:
            stats["rejected_irrelevant"] += 1
            continue
        ok, _ = passes_filters(raw, p)
        if not ok:
            stats["rejected_irrelevant"] += 1
            continue
        sc = score(raw, p.required_skills, portfolio)
        if sc["total"] < p.min_fit:
            stats["rejected_irrelevant"] += 1
            continue
        mails = leads.extract_emails(raw.description)
        has_email = any(m["invited"] for m in mails)
        if p.require_email and not mails:
            stats["rejected_irrelevant"] += 1
            continue
        ease = leads.compute_ease(raw.title, raw.description, raw.engagement_type, sc["geo"], raw.posted_at, has_email)
        if ease[0] < p.min_ease:
            stats["rejected_irrelevant"] += 1
            continue
        scored.append((sc["total"], raw, sc, ease))
    scored.sort(key=lambda t: -t[0])  # best first, so max_results keeps the best, not the earliest
    for _, raw, sc, ease in scored:
        if len(stats["ids"]) >= p.max_results:
            stats["rejected_irrelevant"] += 1  # beyond the per-run cap
            continue
        fp = fingerprint(raw.company_name, raw.title, raw.description)
        existing = find_existing(db, raw, fp)
        if existing and existing.id in seen_in_run or (not existing and fp in seen_fp and raw.company_name):
            stats["rejected_duplicate"] += 1
            continue
        seen_fp.add(fp)
        chash = content_hash(raw.title, raw.description, str(raw.budget_min), str(raw.budget_max),
                             raw.location_requirements)
        now = utcnow()
        company = get_or_create_company(db, raw)
        fields = dict(
            title=raw.title[:500], company_name=raw.company_name[:300], description=raw.description,
            original_url=raw.url[:1000], canonical_url=canonical_url(raw.url)[:1000],
            required_skills=sc["detected_skills"], matched_skills=sc["matched_skills"],
            missing_requirements=sc["missing"], posted_at=raw.posted_at, deadline=raw.deadline,
            engagement_type=raw.engagement_type, remote_status=raw.remote_status,
            location_requirements=raw.location_requirements[:500], budget_min=raw.budget_min,
            budget_max=raw.budget_max, currency=raw.currency, rate_type=raw.rate_type,
            fit_score=sc["total"], score_components={"points": sc["components"], "max": sc["max"],
                                                     "unknown": sc["unknown"], "coverage": sc["data_coverage"]},
            fit_explanation=sc["explanation"], portfolio_evidence=sc["portfolio_evidence"],
            recommended_action=recommend("open", sc["total"], sc["geo"],
                                         any(e["verified"] for e in sc["portfolio_evidence"])),
            ease_score=ease[0], ease_signals=ease[1], apply_method=ease[2],
            company_id=company.id if company else None, last_seen_at=now, last_verified_at=now,
            listing_status="open", content_hash=chash, fingerprint=fp)
        if existing:
            changed = {}
            for k in ("title", "budget_min", "budget_max", "location_requirements", "deadline"):
                if getattr(existing, k) != fields[k]:
                    changed[k] = {"from": str(getattr(existing, k)), "to": str(fields[k])}
            if existing.listing_status != "open":
                changed["listing_status"] = {"from": existing.listing_status, "to": "open"}
            for k, v in fields.items():
                setattr(existing, k, v)
            if changed:
                db.add(OpportunityHistory(opportunity_id=existing.id, run_id=run_id, change=changed))
            opp, is_new = existing, False
        else:
            opp = Opportunity(source_key=raw.source_key, source_type=raw.source_type,
                              external_id=external_id(raw), first_seen_at=now, **fields)
            db.add(opp)
            db.flush()
            is_new = True
            stats["new"] += 1
        if ease[2] == "email" and sc["geo"] != "restricted" and sc["total"] >= 40:
            opp.recommended_action = "Email your application to the address the company published (see Leads); keep it short and specific"
        leads.attach_emails(db, opp, raw.description, "listing", now=now)
        db.add(RunOpportunity(run_id=run_id, opportunity_id=opp.id, is_new=is_new, discovered_at=now))
        seen_in_run.add(opp.id)
        stats["ids"].append(opp.id)
        stats["stored"] += 1
    db.commit()
    return stats


def mark_closed_if_absent(db: Session, source_key: str, run_started, seen_ids: set[int]) -> int:
    """Listings of a fully-fetched API source that disappeared are marked closed (history kept)."""
    n = 0
    rows = db.scalars(select(Opportunity).where(Opportunity.source_key == source_key,
                                                Opportunity.listing_status == "open",
                                                Opportunity.source_type == "api")).all()
    for o in rows:
        if o.id not in seen_ids and o.last_seen_at < run_started:
            o.listing_status = "unknown"  # absent from feed: not proof it is closed
            db.add(OpportunityHistory(opportunity_id=o.id, change={"listing_status": {"from": "open", "to": "unknown"}}))
            n += 1
    db.commit()
    return n
