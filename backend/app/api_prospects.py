from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, schemas
from .db import SessionLocal, get_db
from .models import Application, BusinessContact, Evidence, Opportunity, ProposalDraft
from .services import prospects as svc
from .services.safefetch import SafeFetcher

router = APIRouter(prefix="/api", dependencies=[auth.Authed])
fetcher_factory = SafeFetcher   # replaced in tests


def _d(v):
    return v.isoformat() + "Z" if v else None


def prospect_out(db: Session, o: Opportunity) -> dict:
    meta = o.meta or {}
    offer = svc.OFFERS.get(meta.get("offer", ""), {})
    contacts = db.scalars(svc._usable(select(BusinessContact).where(BusinessContact.opportunity_id == o.id)).order_by(
        BusinessContact.outreach_eligibility != "eligible", BusinessContact.id)).all()
    draft = db.scalar(select(ProposalDraft).where(ProposalDraft.opportunity_id == o.id).order_by(ProposalDraft.id.desc()).limit(1))
    app = db.scalar(select(Application).where(Application.opportunity_id == o.id))
    facts = db.scalars(select(Evidence).where(Evidence.company_id == o.company_id, Evidence.kind == "fact").order_by(Evidence.id).limit(3)).all() if o.company_id else []
    return {
        "id": o.id, "name": o.title, "website": o.original_url, "category": meta.get("category", "company"),
        "offer": meta.get("offer", ""), "offer_label": offer.get("label", ""), "evidence_url": meta.get("evidence_url", ""),
        "evidence_quote": meta.get("evidence_quote", ""), "research_status": o.research_status,
        "need_score": o.ease_score, "signals": o.ease_signals, "relevance": o.fit_score,
        "recommended_action": o.recommended_action, "last_verified_at": _d(o.last_verified_at),
        "added_at": _d(o.first_seen_at), "summary": [f.excerpt for f in facts][:2],
        "contacts": [{"id": c.id, "email": c.email, "eligibility": c.outreach_eligibility, "purpose": c.contact_purpose,
                      "basis": c.eligibility_basis, "source_url": c.source_url, "found_at": _d(c.retrieved_at)} for c in contacts],
        "draft_status": draft.status if draft else "none", "application_status": app.status if app else "none",
        "review_status": o.review_status,
    }


def _get(db: Session, pid: int) -> Opportunity:
    o = db.get(Opportunity, pid)
    if not o or o.source_key != svc.SOURCE:
        raise HTTPException(404, "Prospect not found")
    return o


@router.get("/prospects/meta")
def meta():
    return {"offers": {k: {"label": v["label"], "audience": v["audience"], "deliverable": v["deliverable"],
                           "first_step": v["first_step"]} for k, v in svc.OFFERS.items()},
            "categories": {k: {"label": v["label"], "offer": v["offer"]} for k, v in svc.CATEGORIES.items()}}


@router.get("/prospects")
def list_prospects(db: Session = Depends(get_db), category: str = Query("", pattern="^(|company|agency|network)$"),
                   only_with_mailbox: bool = False):
    rows = db.scalars(select(Opportunity).where(Opportunity.source_key == svc.SOURCE, Opportunity.review_status != "excluded")
                      .order_by(Opportunity.ease_score.desc(), Opportunity.id.desc())).all()
    out = [prospect_out(db, o) for o in rows]
    if category:
        out = [p for p in out if p["category"] == category]
    if only_with_mailbox:
        out = [p for p in out if p["contacts"]]
    return {"total": len(out), "items": out}


@router.post("/prospects")
def add_prospects(body: schemas.ProspectsIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    created, errors, ids = [], [], []
    for it in body.items:
        try:
            o = svc.add_prospect(db, it.website, it.name, it.category, it.offer, it.evidence_url, it.evidence_quote)
        except ValueError as e:
            db.rollback()
            errors.append({"website": it.website, "error": str(e)})
            continue
        created.append(prospect_out(db, o))
        if body.research and o.research_status in ("not_started", "failed"):
            o.research_status = "researching"
            ids.append(o.id)
    db.commit()
    for c in created:
        if c["id"] in ids:
            c["research_status"] = "researching"
    if ids:
        background.add_task(svc.research_many, SessionLocal, ids, lambda: fetcher_factory())
    return {"created": created, "errors": errors}


@router.post("/prospects/{pid}/research")
def research_again(pid: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    o = _get(db, pid)
    if o.research_status == "researching":
        raise HTTPException(409, "Research is already running for this prospect")
    o.research_status = "researching"
    db.commit()
    background.add_task(svc.research_many, SessionLocal, [pid], lambda: fetcher_factory())
    return prospect_out(db, o)


@router.patch("/prospects/{pid}")
def patch_prospect(pid: int, body: schemas.ProspectPatch, db: Session = Depends(get_db)):
    o = _get(db, pid)
    meta = dict(o.meta or {})
    if body.category:
        meta["category"] = body.category
        if body.offer is None:
            meta["offer"], meta["offer_auto"] = svc.CATEGORIES[body.category]["offer"], True
    if body.offer is not None:
        if body.offer not in svc.OFFERS:
            raise HTTPException(422, "Unknown offer")
        meta["offer"], meta["offer_auto"] = body.offer, False
    if body.name:
        o.title = o.company_name = body.name.strip()[:300]
    o.meta = meta
    db.commit()
    return prospect_out(db, o)


@router.delete("/prospects/{pid}")
def remove_prospect(pid: int, db: Session = Depends(get_db)):
    o = _get(db, pid)
    try:
        svc.delete_prospect(db, o)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}
