"""Bring stored opportunities up to date with the current rules (locations, scores). Safe to run at every start."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import hn_hiring
from ..models import Opportunity
from ..portfolio import load_portfolio
from ..scoring import recommend, score
from ..types import RawOpportunity


def refresh_hn_locations(db: Session) -> int:
    """Hacker News location and work arrangement live in the first line of the stored post text; re-derive them with
    the current parser so rows stored by older versions follow the new rules."""
    n = 0
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key == "hn_hiring")).all():
        first = (o.description or "").split("\n", 1)[0]
        loc = hn_hiring._loc(first)
        remote = hn_hiring._remote(first.lower(), (o.description or "").lower())
        if loc != o.location_requirements or remote != o.remote_status:
            o.location_requirements, o.remote_status = loc, remote
            n += 1
    db.commit()
    return n


def rescore_all(db: Session) -> int:
    """Recompute fit, explanation and recommended action for every stored opportunity."""
    pf = load_portfolio()
    n = 0
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key != "prospect")):
        raw = RawOpportunity(source_key=o.source_key, url=o.original_url, title=o.title, company_name=o.company_name,
                             company_website=o.company.website if o.company else "", description=o.description,
                             posted_at=o.posted_at, remote_status=o.remote_status,
                             location_requirements=o.location_requirements, budget_min=o.budget_min,
                             budget_max=o.budget_max, currency=o.currency, rate_type=o.rate_type)
        sc = score(raw, None, pf)
        o.fit_score, o.fit_explanation, o.portfolio_evidence = sc["total"], sc["explanation"], sc["portfolio_evidence"]
        o.score_components = {"points": sc["components"], "max": sc["max"], "unknown": sc["unknown"], "coverage": sc["data_coverage"]}
        keep_email_action = o.apply_method == "email" and sc["total"] >= 40 and sc["geo"] != "restricted"
        o.recommended_action = ("Email your application to the address the company published; keep it short and specific"
                                if keep_email_action else
                                recommend(o.listing_status, sc["total"], sc["geo"], any(e["verified"] for e in sc["portfolio_evidence"])))
        n += 1
    db.commit()
    return n
