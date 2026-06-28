"""Strategy: what to do today and what the stored data says, plus the written playbook (playbook.py).
Nothing here is a forecast. Numbers are counts, a median of what was observed (only with enough observations), or
arithmetic on assumptions the user can change."""
from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Application, BusinessContact, Conversation, Opportunity, ProposalDraft, utcnow
from ..portfolio import load_portfolio
from ..scoring import effective_geo
from . import leads, playbook, prospects
from .exporter import LEAD_MIN_FIT

FREELANCE_TYPES = ("contract", "freelance", "part_time")
TODAY_LIMIT = 5
MIN_RATE_SAMPLE = 8       # fewer hourly-rate listings than this say nothing about the market
MIN_FUNNEL_SAMPLE = 10    # fewer messages than this say nothing about your reply rate
_usable = prospects._usable


def _d(v: datetime | None):
    return v.isoformat() + "Z" if v else None


def _fit(o: Opportunity) -> float:
    return o.score_override if o.score_override is not None else o.fit_score


def _relevant(db: Session) -> list[Opportunity]:
    """Stored listings that fit you (>= LEAD_MIN_FIT), are not excluded and are not restricted to other countries."""
    rows = db.scalars(select(Opportunity).where(
        Opportunity.source_key != prospects.SOURCE, Opportunity.review_status != "excluded",
        func.coalesce(Opportunity.score_override, Opportunity.fit_score) >= LEAD_MIN_FIT)).all()
    return [o for o in rows if effective_geo(o.location_requirements, o.description) != "restricted"]


def _contacts(db: Session, opps: list[Opportunity]) -> dict[int, list[BusinessContact]]:
    """Published application addresses per listing (its own, or its company's). Pitch mailboxes are not application addresses."""
    ids = [o.id for o in opps]
    if not ids:
        return {}
    cids = {o.company_id for o in opps if o.company_id}
    cond = BusinessContact.opportunity_id.in_(ids)
    if cids:
        cond = or_(cond, BusinessContact.company_id.in_(cids))
    by_opp: dict[int, list[BusinessContact]] = {}
    by_company: dict[int, list[BusinessContact]] = {}
    for c in db.scalars(_usable(select(BusinessContact).where(cond, BusinessContact.contact_purpose.notin_(leads.PITCH_PURPOSES)))
                        .order_by(BusinessContact.id)):
        if c.opportunity_id:
            by_opp.setdefault(c.opportunity_id, []).append(c)
        if c.company_id:
            by_company.setdefault(c.company_id, []).append(c)
    out = {}
    for o in opps:
        got = {c.id: c for c in by_opp.get(o.id, [])}
        for c in by_company.get(o.company_id or -1, []):
            got.setdefault(c.id, c)
        if got:
            out[o.id] = sorted(got.values(), key=lambda c: (c.outreach_eligibility != "eligible", c.id))
    return out


def _eng(o: Opportunity) -> int:
    """Contract/freelance work first, then listings that do not say, then employment."""
    return 0 if o.engagement_type in FREELANCE_TYPES else (1 if o.engagement_type == "unknown" else 2)


def _rank(o: Opportunity) -> tuple:
    """Kind of engagement first, then fit and ease of reaching them."""
    return (_eng(o), -((_fit(o) + o.ease_score) / 2), -o.id)


def _lead_item(o: Opportunity, contacts: list[BusinessContact], drafted: set[int]) -> dict:
    return {"id": o.id, "title": o.title, "company": o.company_name, "source": o.source_key, "url": o.original_url,
            "fit": round(_fit(o)), "ease": round(o.ease_score), "engagement": o.engagement_type,
            "location_check": effective_geo(o.location_requirements, o.description), "posted_at": _d(o.posted_at),
            "has_draft": o.id in drafted, "proposal_status": o.proposal_status,
            "emails": [{"email": c.email, "eligibility": c.outreach_eligibility, "source_url": c.source_url} for c in contacts[:3]]}


def _follow_ups(db: Session, now: datetime) -> dict:
    fu = playbook.FOLLOW_UP
    inbound = set(db.scalars(select(Conversation.application_id).where(Conversation.direction == "in")))
    sent: Counter = Counter(db.scalars(select(Conversation.application_id).where(Conversation.direction == "out")))
    due, waiting = [], 0
    for a, o in db.execute(select(Application, Opportunity).join(Opportunity, Opportunity.id == Application.opportunity_id)
                           .where(Application.status == "submitted")).all():
        if a.id in inbound:
            continue                         # they answered: this is a conversation now, not a follow-up
        days, n = (now - a.submitted_at).days, sent[a.id]
        if n >= 2 or days >= fu["close_after_days"]:
            stage = "close"
        elif days >= fu["last_after_days"]:
            stage = "last"
        elif days >= fu["first_after_days"] and n == 0:
            stage = "first"
        else:
            waiting += 1
            continue
        due.append({"application_id": a.id, "opportunity_id": o.id, "title": o.title, "company": o.company_name, "days": days,
                    "stage": stage, "kind": "pitch" if o.source_key == prospects.SOURCE else "application"})
    due.sort(key=lambda r: -r["days"])
    return {"total": len(due), "waiting": waiting, "items": due[:TODAY_LIMIT]}


def _prospect_lists(db: Session) -> dict:
    rows = db.scalars(select(Opportunity).where(Opportunity.source_key == prospects.SOURCE, Opportunity.review_status != "excluded")
                      .order_by(Opportunity.ease_score.desc(), Opportunity.id)).all()
    boxes: Counter = Counter()
    if rows:
        boxes = Counter(db.scalars(_usable(select(BusinessContact.opportunity_id).where(
            BusinessContact.opportunity_id.in_([o.id for o in rows])))))

    def item(o: Opportunity) -> dict:
        meta = o.meta or {}
        return {"id": o.id, "name": o.title, "website": o.original_url, "category": meta.get("category", "company"),
                "offer": prospects.OFFERS.get(meta.get("offer", ""), {}).get("label", ""), "need_score": round(o.ease_score),
                "mailboxes": boxes[o.id], "status": o.research_status, "next": o.recommended_action}

    to_research = [o for o in rows if o.research_status in ("not_started", "failed")]
    ready = [o for o in rows if o.research_status in prospects.STATUSES_DONE and o.application_status == "none"]
    return {"total": len(rows), "contacted": sum(1 for o in rows if o.application_status != "none"),
            "to_research": {"total": len(to_research), "items": [item(o) for o in to_research[:TODAY_LIMIT]]},
            "ready": {"total": len(ready), "items": [item(o) for o in ready[:TODAY_LIMIT]]}}


def _today(db: Session, relevant: list[Opportunity], contacts: dict[int, list[BusinessContact]], now: datetime) -> dict:
    open_ = [o for o in relevant if o.application_status == "none" and o.listing_status != "closed"]
    # within the same kind of engagement an address the company invited applications at comes before one to review
    by_mail = sorted((o for o in open_ if o.id in contacts),
                     key=lambda o: (_eng(o), all(c.outreach_eligibility != "eligible" for c in contacts[o.id])) + _rank(o)[1:])
    by_link = sorted((o for o in open_ if o.id not in contacts and o.engagement_type in FREELANCE_TYPES and o.apply_method != "email"), key=_rank)
    shown = by_mail[:TODAY_LIMIT] + by_link[:TODAY_LIMIT]
    drafted = set(db.scalars(select(ProposalDraft.opportunity_id).where(ProposalDraft.opportunity_id.in_([o.id for o in shown])))) if shown else set()
    pf = load_portfolio()
    return {
        "apply_by_email": {"total": len(by_mail), "items": [_lead_item(o, contacts[o.id], drafted) for o in by_mail[:TODAY_LIMIT]]},
        "apply_by_link": {"total": len(by_link), "items": [_lead_item(o, [], drafted) for o in by_link[:TODAY_LIMIT]]},
        "follow_ups": _follow_ups(db, now),
        "prospects": _prospect_lists(db),
        "portfolio": {"verified": sum(1 for i in pf if i.get("verified")),
                      "unverified": [{"id": i["id"], "title": i.get("title", ""), "note": i.get("verified_note", "")}
                                     for i in pf if not i.get("verified")]},
        "time_plan": playbook.TIME_PLAN,
    }


def _hourly(db: Session) -> dict:
    mids = []
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key != prospects.SOURCE, Opportunity.review_status != "excluded",
                                                  Opportunity.rate_type == "hourly")):
        if (o.currency or "").upper() not in ("USD", "US$", "$") or (o.budget_min is None and o.budget_max is None):
            continue
        lo, hi = (o.budget_min if o.budget_min is not None else o.budget_max), (o.budget_max if o.budget_max is not None else o.budget_min)
        mids.append((lo + hi) / 2)
    n = len(mids)
    if n >= MIN_RATE_SAMPLE:
        return {"n": n, "median_usd": round(statistics.median(mids), 1), "min_usd": round(min(mids), 1), "max_usd": round(max(mids), 1),
                "note": f"Median of the midpoints of {n} listings that state an hourly rate in USD. Listings that state a rate are not all listings."}
    return {"n": n, "median_usd": None, "min_usd": None, "max_usd": None,
            "note": f"Only {n} stored listings state an hourly rate in USD. That is too few to say what the market pays, so no figure is shown."}


def _market(db: Session, relevant: list[Opportunity], contacts: dict[int, list[BusinessContact]], portfolio: list[dict]) -> dict:
    n = len(relevant)
    shown = {s.lower() for i in portfolio if i.get("verified") for s in i.get("skills", [])}
    skills = Counter(s for o in relevant for s in set(o.required_skills or []))
    per_source: dict[str, dict] = {}
    for o in relevant:
        row = per_source.setdefault(o.source_key, {"source": o.source_key, "fitting": 0, "contract_or_freelance": 0, "with_email": 0})
        row["fitting"] += 1
        row["contract_or_freelance"] += o.engagement_type in FREELANCE_TYPES
        row["with_email"] += o.id in contacts
    return {
        "fitting_listings": n,
        "engagement": dict(Counter(o.engagement_type for o in relevant).most_common()),
        "skills": [{"skill": s, "count": c, "share_percent": round(100 * c / n), "verified_evidence": s.lower() in shown}
                   for s, c in skills.most_common(10)],
        "sources": sorted(per_source.values(), key=lambda r: (-r["with_email"], -r["contract_or_freelance"], -r["fitting"])),
        "hourly": _hourly(db),
    }


def _funnel(db: Session) -> dict:
    rows = db.execute(select(Application, Opportunity.source_key).join(Opportunity, Opportunity.id == Application.opportunity_id)).all()
    inbound = set(db.scalars(select(Conversation.application_id).where(Conversation.direction == "in")))
    total = len(rows)
    replied = sum(1 for a, _ in rows if a.status in ("replied", "interview", "won") or a.id in inbound)
    won = sum(1 for a, _ in rows if a.status == "won")
    enough = total >= MIN_FUNNEL_SAMPLE
    return {"messages_sent": total, "pitches": sum(1 for _, k in rows if k == prospects.SOURCE), "replies": replied, "won": won,
            "reply_rate_percent": round(100 * replied / total) if enough else None,
            "win_rate_percent": round(100 * won / total) if enough else None,
            "note": ("Rates are shown once you have logged at least "
                     f"{MIN_FUNNEL_SAMPLE} messages; with fewer, a percentage would only look precise.") if not enough else
                    "Measured from the messages you logged in Pipeline."}


def _offers(portfolio: list[dict]) -> list[dict]:
    """An offer is 'ready' when a verified portfolio item shows its defining skill (the first one listed for the offer)."""
    verified = [i for i in portfolio if i.get("verified")]
    out = []
    for key, o in prospects.OFFERS.items():
        if key == "network_application":
            continue
        core = o["skills"][0].lower()
        backing = [i.get("title", "") for i in verified if core in {s.lower() for s in i.get("skills", [])}]
        out.append({"key": key, "label": o["label"], "audience": o["audience"], "deliverable": o["deliverable"],
                    "first_step": o["first_step"], "core_skill": o["skills"][0], "ready": bool(backing), "backed_by": backing[:3]})
    return sorted(out, key=lambda r: not r["ready"])


def _income() -> dict:
    a = playbook.INCOME
    hours = a["hours_per_day"] * a["days_per_month"]
    billable = hours * a["billable_share"]
    return {"assumptions": {k: a[k] for k in ("hours_per_day", "days_per_month", "billable_share")},
            "hours_per_month": hours, "billable_hours": billable, "note": a["note"],
            "rows": [{"target": t, "hourly_needed": round(t / billable),
                      "projects": [{"price": p, "count": math.ceil(t / p)} for p in a["prices"]]} for t in a["targets"]]}


def build(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    portfolio = load_portfolio()
    relevant = _relevant(db)
    contacts = _contacts(db, relevant)
    return {
        "generated_at": _d(now), "checked": playbook.CHECKED,
        "today": _today(db, relevant, contacts, now),
        "market": _market(db, relevant, contacts, portfolio),
        "funnel": _funnel(db),
        "offers": _offers(portfolio),
        "income": _income(),
        "channels": playbook.CHANNELS, "networks": playbook.NETWORKS, "not_now": playbook.NOT_NOW,
        "message": playbook.MESSAGE, "follow_up": playbook.FOLLOW_UP, "week": playbook.WEEK,
        "spend_plan": playbook.SPEND_PLAN, "rules": playbook.RULES, "why_not_upwork": playbook.WHY_NOT_UPWORK,
    }
