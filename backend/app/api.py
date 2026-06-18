from __future__ import annotations

import csv
import hashlib
import io
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, object_session

from . import auth, schemas
from .config import get_settings
from .db import get_db
from .models import (Application, BusinessContact, Company, Conversation, Evidence, ExportRecord, Opportunity,
                     OpportunityHistory, ProposalDraft, ResearchRun, RunOpportunity, SearchProfile, Source,
                     Suppression, UsageEvent, utcnow)
from .portfolio import load_portfolio, save_portfolio
from .scoring import geo_status, recommend, score
from .services import alerts as alerts_svc
from .services import contacts as contacts_svc
from .services import drafting, exporter, pipeline, research, runner, usage
from .services.backup import backup_database
from .services.safefetch import SafeFetcher
from .textutil import canonical_url
from .types import RawOpportunity, SearchParams

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[auth.Authed])


def _d(v):
    return v.isoformat() + "Z" if v else None


# ---------------------------------------------------------------- auth / health
@public.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "auth_enabled": auth.auth_enabled()}


@public.post("/auth/login")
def login(body: schemas.LoginIn, response: Response):
    import hmac
    if not auth.auth_enabled():
        return {"ok": True, "auth_enabled": False}
    if not hmac.compare_digest(body.password.encode(), get_settings().app_password.encode()):
        raise HTTPException(401, "Wrong password")
    response.set_cookie(auth.COOKIE, auth.make_token(), httponly=True, samesite="strict",
                        secure=get_settings().cookie_secure, max_age=auth.MAX_AGE)
    return {"ok": True, "auth_enabled": True}


@public.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@public.get("/auth/me")
def me(request: Request):
    return {"auth_enabled": auth.auth_enabled(),
            "authenticated": (not auth.auth_enabled()) or auth.valid_token(request.cookies.get(auth.COOKIE))}


# ---------------------------------------------------------------- overview
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    c = lambda q: db.scalar(q) or 0  # noqa: E731
    last = db.scalar(select(ResearchRun).where(ResearchRun.status.in_(("completed", "partial")))
                     .order_by(ResearchRun.id.desc()).limit(1))
    s = get_settings()
    fails = c(select(func.count()).select_from(Company).where(Company.research_status == "failed"))
    failed_runs = c(select(func.count()).select_from(ResearchRun).where(ResearchRun.status == "failed"))
    est = float(c(select(func.sum(UsageEvent.cost_usd)).where(UsageEvent.estimated.is_(True))))
    act = float(c(select(func.sum(UsageEvent.cost_usd)).where(UsageEvent.estimated.is_(False))))
    apps = lambda *st: c(select(func.count()).select_from(Application).where(Application.status.in_(st)))  # noqa: E731
    return {
        "opportunities_total": c(select(func.count()).select_from(Opportunity)),
        "new_since_previous_run": last.new_count if last else 0,
        "relevant": c(select(func.count()).select_from(Opportunity).where(Opportunity.fit_score >= 40,
                                                                          Opportunity.review_status != "excluded")),
        "awaiting_review": c(select(func.count()).select_from(Opportunity).where(
            Opportunity.review_status == "new", Opportunity.fit_score >= 40)),
        "proposals_drafted": c(select(func.count(func.distinct(ProposalDraft.opportunity_id)))),
        "applications_submitted": c(select(func.count()).select_from(Application)),
        "replies": apps("replied"), "interviews": apps("interview"), "won": apps("won"), "lost": apps("lost"),
        "research_failures": fails + failed_runs,
        "cost_estimated_usd": round(est, 4), "cost_actual_usd": round(act, 4),
        "month_spend_usd": round(usage.month_spend(db), 4), "monthly_budget_usd": s.monthly_budget_usd,
        "runs_total": c(select(func.count()).select_from(ResearchRun)),
        "last_run": run_out(last) if last else None,
        "contacts_total": c(select(func.count()).select_from(BusinessContact)),
        "emails_found": c(select(func.count()).select_from(BusinessContact).where(
            BusinessContact.source_url != "", BusinessContact.suppressed.is_(False),
            BusinessContact.outreach_eligibility != "not_eligible")),
        "apply_by_email_leads": c(select(func.count()).select_from(Opportunity).where(
            Opportunity.apply_method == "email", Opportunity.review_status != "excluded")),
        "llm_enabled": s.llm_enabled and bool(s.anthropic_api_key),
        "auth_enabled": auth.auth_enabled(),
    }


# ---------------------------------------------------------------- sources / profiles
@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    s = get_settings()
    rows = db.scalars(select(Source).order_by(Source.id)).all()
    return [{"key": r.key, "name": r.name, "kind": r.kind, "enabled": r.enabled, "verified": r.verified,
             "docs_url": r.docs_url, "terms_url": r.terms_url, "notes": r.notes, "checked_at": r.checked_at,
             "configured": r.kind in ("api", "alert", "manual")} for r in rows]


@router.get("/profiles")
def profiles(db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name, "params": p.params, "is_preset": p.is_preset}
            for p in db.scalars(select(SearchProfile).order_by(SearchProfile.id))]


@router.post("/profiles")
def create_profile(body: schemas.ProfileIn, db: Session = Depends(get_db)):
    if db.scalar(select(SearchProfile).where(SearchProfile.name == body.name)):
        raise HTTPException(409, "A profile with this name exists")
    p = SearchProfile(name=body.name, params=body.params.model_dump())
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.delete("/profiles/{pid}")
def delete_profile(pid: int, db: Session = Depends(get_db)):
    p = db.get(SearchProfile, pid)
    if not p:
        raise HTTPException(404)
    if p.is_preset:
        raise HTTPException(400, "Preset profiles cannot be deleted")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- runs
def run_out(r: ResearchRun) -> dict:
    emails_found = len(exporter.run_emails(object_session(r), r.id))
    dur = None
    if r.started_at:
        dur = int(((r.finished_at or utcnow()) - r.started_at).total_seconds())
    return {"id": r.id, "profile_name": r.profile_name, "status": r.status, "created_at": _d(r.created_at),
            "started_at": _d(r.started_at), "finished_at": _d(r.finished_at), "duration_s": dur,
            "current_source": r.current_source, "sources_queried": r.sources_queried,
            "source_results": r.source_results, "discovered": r.discovered, "stored": r.stored,
            "new_count": r.new_count, "rejected_irrelevant": r.rejected_irrelevant,
            "rejected_duplicate": r.rejected_duplicate, "selected_for_review": r.selected_for_review,
            "companies_researched": r.companies_researched, "drafts_generated": r.drafts_generated,
            "cost_usd": round(r.cost_usd, 4), "retry_count": r.retry_count, "last_error": r.last_error,
            "errors": r.errors, "incomplete_notes": r.incomplete_notes, "info_notes": r.info_notes, "export_status": r.export_status,
            "cancel_requested": r.cancel_requested, "params": r.params, "emails_found": emails_found,
            "exports": [export_out(e) for e in r.exports]}


@router.post("/runs")
def start_run(body: schemas.RunIn, db: Session = Depends(get_db)):
    if body.profile_id:
        prof = db.get(SearchProfile, body.profile_id)
        if not prof:
            raise HTTPException(404, "Profile not found")
        params = dict(prof.params)
    elif body.search:
        params = body.search.model_dump()
    else:
        raise HTTPException(422, "Provide profile_id or search")
    if usage.month_spend(db) >= get_settings().monthly_budget_usd:
        params["max_drafts"] = 0  # paid work blocked; free retrieval still allowed
    run = runner.create_run(db, params, body.profile_id)
    return run_out(run)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db), limit: int = Query(50, le=200)):
    return [run_out(r) for r in db.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(limit))]


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    r = db.get(ResearchRun, rid)
    if not r:
        raise HTTPException(404)
    return run_out(r)


@router.post("/runs/{rid}/cancel")
def cancel(rid: int, db: Session = Depends(get_db)):
    r = db.get(ResearchRun, rid)
    if not r:
        raise HTTPException(404)
    runner.cancel_run(db, r)
    return run_out(r)


@router.post("/runs/{rid}/retry")
def retry(rid: int, db: Session = Depends(get_db)):
    r = db.get(ResearchRun, rid)
    if not r:
        raise HTTPException(404)
    if r.status in ("pending", "running"):
        raise HTTPException(409, "Run is still active")
    return run_out(runner.create_run(db, r.params, r.profile_id, retry_of=r))


@router.get("/runs/{rid}/opportunities")
def run_opps(rid: int, db: Session = Depends(get_db)):
    ids = db.scalars(select(RunOpportunity.opportunity_id).where(RunOpportunity.run_id == rid)).all()
    rows = db.scalars(select(Opportunity).where(Opportunity.id.in_(ids)).order_by(Opportunity.fit_score.desc())).all()
    return [opp_out(o) for o in rows]


@router.post("/runs/{rid}/export")
def export_again(rid: int, db: Session = Depends(get_db)):
    """Export CSV button / retry after a failed export. Creates a NEW file; never overwrites."""
    r = db.get(ResearchRun, rid)
    if not r:
        raise HTTPException(404)
    if r.status in ("pending", "running"):
        raise HTTPException(409, "Run is still active")
    a, b = exporter.export_run_bundle(db, r)
    return export_out(a) | {"emails": export_out(b)}


# ---------------------------------------------------------------- exports
def export_out(e: ExportRecord) -> dict:
    return {"id": e.id, "run_id": e.run_id, "kind": e.kind, "filename": e.filename, "created_at": _d(e.created_at),
            "row_count": e.row_count, "status": e.status, "error": e.error, "run_status": e.run_status,
            "sha256": e.sha256, "download_url": f"/api/exports/{e.id}/download" if e.status == "ok" else None}


@router.get("/exports")
def list_exports(db: Session = Depends(get_db)):
    return [export_out(e) for e in db.scalars(select(ExportRecord).order_by(ExportRecord.id.desc()).limit(200))]


@router.get("/exports/download-all")
def download_all(kind: str = Query("", pattern="^(|opportunities|emails)$"), run_id: int | None = None,
                 db: Session = Depends(get_db)):
    """One ZIP with every stored CSV (optionally only one kind, or only one run), plus manifest.csv.
    Files are read from disk and checked against their recorded SHA-256; a file that is missing or was
    modified after export is left out and listed in the manifest instead of being served as the original."""
    stmt = select(ExportRecord).where(ExportRecord.status == "ok").order_by(ExportRecord.id)
    if kind:
        stmt = stmt.where(ExportRecord.kind == kind)
    if run_id is not None:
        stmt = stmt.where(ExportRecord.run_id == run_id)
    records = db.scalars(stmt).all()
    if not records:
        raise HTTPException(404, "No exports to download yet. Run a research first.")
    exports_dir = get_settings().exports_dir.resolve()
    manifest = io.StringIO()
    w = csv.writer(manifest)
    w.writerow(["file_in_zip", "kind", "run_id", "rows", "created_at", "sha256", "included", "note"])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    included = 0
    try:
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
            for e in records:
                path, note, data = Path(e.path), "", None
                if not path.is_file() or path.resolve().parent != exports_dir:
                    note = "file missing on disk"
                else:
                    data = path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != e.sha256:
                        data, note = None, "file was modified after export; not included"
                name = f"{e.kind}/{e.filename}"
                w.writerow([name if data is not None else "", e.kind, e.run_id or "", e.row_count,
                            _d(e.created_at), e.sha256, "yes" if data is not None else "no", note])
                if data is not None:
                    z.writestr(name, data)
                    included += 1
            z.writestr("manifest.csv", "\ufeff" + manifest.getvalue())
        if included == 0:
            raise HTTPException(409, "The export files are missing or were changed on disk; nothing to download")
    except Exception:
        os.unlink(tmp.name)
        raise
    stamp = utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    label = f"run{run_id}_" if run_id is not None else ""
    return FileResponse(tmp.name, media_type="application/zip", background=BackgroundTask(os.unlink, tmp.name),
                        filename=f"clienthunt_csvs_{label}{kind + '_' if kind else ''}{stamp}.zip")


@router.post("/exports/contacts")
def export_contacts(db: Session = Depends(get_db)):
    return export_out(exporter.export_contacts(db))


@router.get("/exports/{eid}/download")
def download(eid: int, db: Session = Depends(get_db)):
    e = db.get(ExportRecord, eid)
    if not e or e.status != "ok":
        raise HTTPException(404, "Export not found")
    p = Path(e.path)
    if not p.is_file() or p.resolve().parent != get_settings().exports_dir.resolve():
        raise HTTPException(404, "File missing on disk")
    if hashlib.sha256(p.read_bytes()).hexdigest() != e.sha256:
        raise HTTPException(409, "File on disk was modified after export; refusing to serve it as the original")
    return FileResponse(p, media_type="text/csv; charset=utf-8", filename=e.filename)


# ---------------------------------------------------------------- opportunities
def opp_out(o: Opportunity, detail: bool = False) -> dict:
    d = {"id": o.id, "title": o.title, "source": o.source_key, "source_type": o.source_type, "url": o.original_url,
         "company_name": o.company_name, "company_id": o.company_id,
         "company_website": o.company.website if o.company else "",
         "description": o.description if detail else o.description[:400],
         "required_skills": o.required_skills, "matched_skills": o.matched_skills,
         "budget_min": o.budget_min, "budget_max": o.budget_max, "currency": o.currency, "rate_type": o.rate_type,
         "posted_at": _d(o.posted_at), "deadline": _d(o.deadline), "engagement_type": o.engagement_type,
         "remote_status": o.remote_status, "location_requirements": o.location_requirements,
         "portfolio_evidence": o.portfolio_evidence,
         "fit_score": o.score_override if o.score_override is not None else o.fit_score,
         "auto_score": o.fit_score, "score_override": o.score_override,
         "score_components": o.score_components, "fit_explanation": o.fit_explanation,
         "missing_requirements": o.missing_requirements, "recommended_action": o.recommended_action,
         "research_status": o.research_status, "last_verified_at": _d(o.last_verified_at),
         "listing_status": o.listing_status, "review_status": o.review_status,
         "exclusion_reason": o.exclusion_reason, "proposal_status": o.proposal_status,
         "application_status": o.application_status, "first_seen_at": _d(o.first_seen_at),
         "ease_score": o.ease_score, "ease_signals": o.ease_signals, "apply_method": o.apply_method}
    return d


@router.get("/opportunities")
def list_opps(db: Session = Depends(get_db), q: str = "", source: str = "", min_score: float = 0,
              review_status: str = "", engagement: str = "", show_excluded: bool = False,
              sort: str = "score", limit: int = Query(200, le=1000), offset: int = 0):
    stmt = select(Opportunity)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.company_name.ilike(like),
                              Opportunity.description.ilike(like)))
    if source:
        stmt = stmt.where(Opportunity.source_key == source)
    if review_status:
        stmt = stmt.where(Opportunity.review_status == review_status)
    elif not show_excluded:
        stmt = stmt.where(Opportunity.review_status != "excluded")
    if engagement:
        stmt = stmt.where(Opportunity.engagement_type == engagement)
    stmt = stmt.where(func.coalesce(Opportunity.score_override, Opportunity.fit_score) >= min_score)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"score": func.coalesce(Opportunity.score_override, Opportunity.fit_score).desc(),
             "ease": Opportunity.ease_score.desc(),
             "newest": Opportunity.first_seen_at.desc(), "posted": Opportunity.posted_at.desc()}.get(sort)
    stmt = stmt.order_by(order, Opportunity.id.desc()).limit(limit).offset(offset)
    return {"total": total, "items": [opp_out(o) for o in db.scalars(stmt)]}


def _opp(db: Session, oid: int) -> Opportunity:
    o = db.get(Opportunity, oid)
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return o


@router.get("/opportunities/{oid}")
def get_opp(oid: int, db: Session = Depends(get_db)):
    o = _opp(db, oid)
    out = opp_out(o, detail=True)
    out["history"] = [{"at": _d(h.at), "change": h.change} for h in
                      db.scalars(select(OpportunityHistory).where(OpportunityHistory.opportunity_id == oid)
                                 .order_by(OpportunityHistory.id.desc()))]
    ev = []
    if o.company_id:
        ev = db.scalars(select(Evidence).where(Evidence.company_id == o.company_id).order_by(Evidence.id)).all()
    out["evidence"] = [{"id": e.id, "kind": e.kind, "claim": e.claim, "excerpt": e.excerpt, "source_url": e.source_url,
                        "retrieved_at": _d(e.retrieved_at), "confidence": e.confidence, "approved": e.approved} for e in ev]
    out["company"] = ({"id": o.company.id, "name": o.company.name, "website": o.company.website,
                       "website_source": o.company.website_source, "description": o.company.description,
                       "research_status": o.company.research_status, "researched_at": _d(o.company.researched_at),
                       "last_error": o.company.last_error} if o.company else None)
    out["drafts"] = [draft_out(d) for d in db.scalars(select(ProposalDraft).where(ProposalDraft.opportunity_id == oid)
                                                      .order_by(ProposalDraft.id.desc()))]
    app = db.scalar(select(Application).where(Application.opportunity_id == oid))
    out["application"] = app_out(db, app) if app else None
    out["contacts"] = [contact_out(c) for c in db.scalars(select(BusinessContact).where(
        BusinessContact.opportunity_id == oid, BusinessContact.source_url != "",
        BusinessContact.suppressed.is_(False), BusinessContact.outreach_eligibility != "not_eligible"))]
    return out


@router.patch("/opportunities/{oid}")
def patch_opp(oid: int, body: schemas.OppPatch, db: Session = Depends(get_db)):
    o = _opp(db, oid)
    if body.review_status:
        o.review_status = body.review_status
    if body.exclusion_reason is not None:
        o.exclusion_reason = body.exclusion_reason
    if body.clear_score_override:
        o.score_override = None
    elif body.score_override is not None:
        o.score_override = body.score_override
    if body.company_website is not None:
        if not o.company_id:
            raise HTTPException(400, "Opportunity has no company; cannot attach a website")
        w = body.company_website.strip()
        if w and not w.startswith(("http://", "https://")):
            raise HTTPException(422, "Website must start with http:// or https://")
        o.company.website, o.company.website_source = w, "user"
        o.company.research_status = "not_started"
    db.commit()
    return opp_out(o, True)


@router.post("/opportunities/manual")
def add_manual(body: schemas.ManualIn, db: Session = Depends(get_db)):
    raw = RawOpportunity(source_key="manual", url=body.url, title=body.title, company_name=body.company_name,
                         company_website=body.company_website, company_website_source="user" if body.company_website else "",
                         description=body.description, engagement_type=body.engagement_type,
                         location_requirements=body.location_requirements, budget_min=body.budget_min,
                         budget_max=body.budget_max, currency=body.currency, rate_type=body.rate_type,
                         source_type="manual")
    return _ingest_adhoc(db, [raw], "Manual entry")


def _ingest_adhoc(db: Session, raws: list[RawOpportunity], name: str) -> dict:
    run = runner.create_run(db, {"name": name, "min_fit": 0, "remote_only": False, "posted_within_days": None,
                                 "sources": [], "max_results": 500}, None)
    run.status, run.started_at = "running", utcnow()
    db.commit()
    p = SearchParams(min_fit=0, remote_only=False, posted_within_days=None, max_results=500)
    stats = pipeline.process(db, raws, p, run.id)
    run.discovered, run.stored, run.new_count = stats["discovered"], stats["stored"], stats["new"]
    run.rejected_duplicate = stats["rejected_duplicate"]
    run.rejected_irrelevant = stats["rejected_irrelevant"]
    run.status, run.finished_at = "completed", utcnow()
    run.sources_queried = sorted({r.source_key for r in raws})
    db.commit()
    exporter.export_run_bundle(db, run)
    return {"run": run_out(run), "opportunity_ids": stats["ids"]}


@router.post("/alerts/import")
def import_alerts(body: schemas.AlertIn, db: Session = Depends(get_db)):
    raws = alerts_svc.parse_alert(body.text, body.platform_hint.strip().lower())
    return _ingest_adhoc(db, raws, "Alert import") | {"parsed": len(raws)}


@router.post("/opportunities/{oid}/research")
def research_opp(oid: int, db: Session = Depends(get_db)):
    o = _opp(db, oid)
    if not o.company:
        raise HTTPException(400, "No company is named in this listing")
    if not o.company.website:
        raise HTTPException(400, "No official website known. Add it (from the company's own site) and retry")
    n = research.research_company(db, o.company, o, SafeFetcher())
    return {"evidence_added": n, "status": o.company.research_status, "error": o.company.last_error}


@router.post("/opportunities/{oid}/recheck")
def recheck(oid: int, db: Session = Depends(get_db)):
    """Re-verify the listing is still reachable before applying (Himalayas-style open check not generic)."""
    o = _opp(db, oid)
    try:
        f = SafeFetcher()
        f.get_html(o.original_url)
        o.listing_status, o.last_verified_at = "open", utcnow()
        msg = "Listing URL still reachable (this does not prove it still accepts applications)."
    except Exception as e:  # noqa: BLE001
        o.listing_status = "unknown"
        msg = f"Could not confirm: {e}"
    db.commit()
    return {"listing_status": o.listing_status, "message": msg}


@router.post("/evidence/{eid}")
def approve_evidence(eid: int, body: schemas.EvidenceApprove, db: Session = Depends(get_db)):
    e = db.get(Evidence, eid)
    if not e:
        raise HTTPException(404)
    if e.kind != "fact" and body.approved:
        raise HTTPException(400, "Hypotheses cannot be approved as facts")
    e.approved = body.approved
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- drafts
def draft_out(d: ProposalDraft) -> dict:
    return {"id": d.id, "opportunity_id": d.opportunity_id, "version": d.version, "body": d.body, "status": d.status,
            "generator": d.generator, "rationale": d.rationale, "warnings": d.warnings,
            "portfolio_ids": d.portfolio_ids, "evidence_ids": d.evidence_ids, "est_cost_usd": d.est_cost_usd,
            "created_at": _d(d.created_at), "approved_at": _d(d.approved_at)}


@router.post("/opportunities/{oid}/drafts")
def new_draft(oid: int, db: Session = Depends(get_db)):
    o = _opp(db, oid)
    if o.listing_status == "closed":
        raise HTTPException(409, "Listing is marked closed")
    return draft_out(drafting.generate_draft(db, o))


def _draft(db: Session, did: int) -> ProposalDraft:
    d = db.get(ProposalDraft, did)
    if not d:
        raise HTTPException(404)
    return d


@router.patch("/drafts/{did}")
def edit_draft(did: int, body: schemas.DraftPatch, db: Session = Depends(get_db)):
    d = _draft(db, did)
    d.body = body.body
    new_hash = hashlib.sha256(body.body.encode()).hexdigest()
    if new_hash != d.body_hash:
        d.status, d.approved_at = "draft", None  # editing cancels approval
        d.body_hash = new_hash
        o = _opp(db, d.opportunity_id)
        facts = db.scalars(select(Evidence).where(Evidence.company_id == o.company_id, Evidence.kind == "fact",
                                                  Evidence.approved.is_(True))).all() if o.company_id else []
        allowed = {i["url"] for i in load_portfolio() if i["id"] in d.portfolio_ids and i.get("url")
                   and o.source_key in drafting.DIRECT_SOURCES}
        d.warnings = drafting.check_claims(body.body, o, allowed, facts)
    db.commit()
    return draft_out(d)


@router.post("/drafts/{did}/approve")
def approve_draft(did: int, body: schemas.ApproveIn, db: Session = Depends(get_db)):
    d = _draft(db, did)
    if d.warnings and not body.acknowledge_warnings:
        raise HTTPException(409, {"message": "Draft has unsupported-claim warnings; acknowledge them to approve",
                                  "warnings": d.warnings})
    d.status, d.approved_at = "approved", utcnow()
    o = _opp(db, d.opportunity_id)
    o.proposal_status = "approved"  # approved != submitted
    db.commit()
    return draft_out(d)


@router.post("/drafts/{did}/reject")
def reject_draft(did: int, db: Session = Depends(get_db)):
    d = _draft(db, did)
    d.status, d.approved_at = "rejected", None
    db.commit()
    return draft_out(d)


# ---------------------------------------------------------------- applications
def app_out(db: Session, a: Application) -> dict:
    convs = db.scalars(select(Conversation).where(Conversation.application_id == a.id).order_by(Conversation.id)).all()
    return {"id": a.id, "opportunity_id": a.opportunity_id, "draft_id": a.draft_id, "status": a.status,
            "submitted_at": _d(a.submitted_at), "updated_at": _d(a.updated_at), "notes": a.notes,
            "conversations": [{"id": c.id, "direction": c.direction, "at": _d(c.at), "summary": c.summary} for c in convs]}


@router.post("/opportunities/{oid}/applications")
def record_application(oid: int, body: schemas.ApplicationIn, db: Session = Depends(get_db)):
    """Records that YOU submitted on the platform. Requires an approved draft; this app never submits."""
    o = _opp(db, oid)
    if db.scalar(select(Application).where(Application.opportunity_id == oid)):
        raise HTTPException(409, "Application already recorded")
    d = db.get(ProposalDraft, body.draft_id) if body.draft_id else db.scalar(
        select(ProposalDraft).where(ProposalDraft.opportunity_id == oid, ProposalDraft.status == "approved")
        .order_by(ProposalDraft.id.desc()))
    if not d or d.status != "approved" or d.opportunity_id != oid:
        raise HTTPException(409, "An approved draft is required before recording a submission")
    a = Application(opportunity_id=oid, draft_id=d.id, notes=body.notes)
    o.application_status, o.proposal_status = "submitted", "submitted"
    db.add(a)
    db.commit()
    return app_out(db, a)


@router.get("/applications")
def list_apps(db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(Application).order_by(Application.id.desc())):
        o = db.get(Opportunity, a.opportunity_id)
        out.append(app_out(db, a) | {"title": o.title, "company_name": o.company_name, "url": o.original_url})
    return out


@router.patch("/applications/{aid}")
def patch_app(aid: int, body: schemas.ApplicationPatch, db: Session = Depends(get_db)):
    a = db.get(Application, aid)
    if not a:
        raise HTTPException(404)
    a.status, a.updated_at = body.status, utcnow()
    if body.notes is not None:
        a.notes = body.notes
    db.get(Opportunity, a.opportunity_id).application_status = body.status
    db.commit()
    return app_out(db, a)


@router.post("/applications/{aid}/conversations")
def add_conv(aid: int, body: schemas.ConversationIn, db: Session = Depends(get_db)):
    a = db.get(Application, aid)
    if not a:
        raise HTTPException(404)
    db.add(Conversation(application_id=aid, direction=body.direction, summary=body.summary))
    db.commit()
    return app_out(db, a)


# ---------------------------------------------------------------- leads (hiring + published emails)
def contact_out(c: BusinessContact) -> dict:
    return {"id": c.id, "email": c.email, "type": "role / generic mailbox" if c.is_generic else "individual address (as published)",
            "purpose": c.contact_purpose, "eligibility": c.outreach_eligibility, "basis": c.eligibility_basis,
            "source_url": c.source_url, "found_at": _d(c.retrieved_at), "context": c.source_note,
            "verified_status": c.verified_status}


@router.get("/leads")
def leads(db: Session = Depends(get_db), has_email: bool = True, hide_restricted: bool = True, min_ease: float = 0,
          min_fit: float = 0, q: str = "", sort: str = "best", limit: int = Query(300, le=1000)):
    stmt = select(Opportunity).where(Opportunity.review_status != "excluded", Opportunity.ease_score >= min_ease,
                                     func.coalesce(Opportunity.score_override, Opportunity.fit_score) >= min_fit)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Opportunity.title.ilike(like), Opportunity.company_name.ilike(like),
                              Opportunity.description.ilike(like)))
    fit = func.coalesce(Opportunity.score_override, Opportunity.fit_score)
    order = {"ease": Opportunity.ease_score.desc(), "fit": fit.desc()}.get(sort, ((Opportunity.ease_score + fit) / 2).desc())
    opps = db.scalars(stmt.order_by(order, Opportunity.id.desc()).limit(2000)).all()
    ids = [o.id for o in opps]
    by_opp: dict[int, list[BusinessContact]] = {}
    if ids:
        for c in db.scalars(select(BusinessContact).where(
                BusinessContact.opportunity_id.in_(ids), BusinessContact.source_url != "",
                BusinessContact.suppressed.is_(False), BusinessContact.outreach_eligibility != "not_eligible")
                .order_by(BusinessContact.id)):
            by_opp.setdefault(c.opportunity_id, []).append(c)
    items = []
    for o in opps:
        cs = by_opp.get(o.id, [])
        if has_email and not cs:
            continue
        if hide_restricted and geo_status(o.location_requirements) == "restricted":
            continue
        d = opp_out(o)
        d["contacts"] = [contact_out(c) for c in sorted(cs, key=lambda c: (c.outreach_eligibility != "eligible", c.id))]
        items.append(d)
        if len(items) >= limit:
            break
    emails = {c["email"] for i in items for c in i["contacts"]}
    return {"total": len(items), "emails": sorted(emails), "items": items}


@router.post("/exports/emails")
def export_emails(db: Session = Depends(get_db)):
    """Download-ready CSV of every stored address that has a source URL (not suppressed / not_eligible)."""
    return export_out(exporter.export_all_emails(db))


# ---------------------------------------------------------------- contacts (separate from opportunities)
@router.get("/contacts")
def list_contacts(db: Session = Depends(get_db), q: str = "", eligibility: str = "", limit: int = Query(100, le=500),
                  offset: int = 0):
    stmt = select(BusinessContact)
    if q:
        stmt = stmt.where(or_(BusinessContact.email_norm.ilike(f"%{q.lower()}%"),
                              BusinessContact.company_name.ilike(f"%{q}%"), BusinessContact.name.ilike(f"%{q}%")))
    if eligibility:
        stmt = stmt.where(BusinessContact.outreach_eligibility == eligibility)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(BusinessContact.id).limit(limit).offset(offset)).all()
    by_elig = dict(db.execute(select(BusinessContact.outreach_eligibility, func.count())
                              .group_by(BusinessContact.outreach_eligibility)).all())
    return {"total": total, "by_eligibility": by_elig, "items": [
        {"id": c.id, "email": c.email, "name": c.name, "role": c.role, "company_name": c.company_name,
         "is_generic": c.is_generic, "source_type": c.source_type, "source_url": c.source_url,
         "provenance_missing": not c.source_url, "verified_status": c.verified_status,
         "outreach_eligibility": c.outreach_eligibility, "eligibility_basis": c.eligibility_basis,
         "suppressed": c.suppressed} for c in rows]}


@router.post("/contacts")
def add_contact(body: schemas.ContactIn, db: Session = Depends(get_db)):
    norm = body.email.strip().lower()
    if not contacts_svc._EMAIL.match(norm):
        raise HTTPException(422, "Invalid email syntax")
    if db.scalar(select(BusinessContact.id).where(BusinessContact.email_norm == norm)):
        raise HTTPException(409, "Contact already exists")
    c = BusinessContact(email=body.email.strip(), email_norm=norm, domain=norm.split("@")[1], name=body.name,
                        role=body.role, company_name=body.company_name, source_type="public_web",
                        source_url=body.source_url, source_note=body.source_note, retrieved_at=utcnow(),
                        is_generic=norm.split("@")[0] in contacts_svc.GENERIC,
                        suppressed=contacts_svc.is_suppressed(db, norm))
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.post("/contacts/import")
async def import_contacts(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import tempfile
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "Upload an .xlsx file")
    data = await file.read()
    if len(data) > 50_000_000:
        raise HTTPException(413, "File too large")
    backup = None
    try:
        backup = str(backup_database())
    except RuntimeError:
        pass
    with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            stats = contacts_svc.import_contacts_file(db, Path(tmp.name), f"Imported from {file.filename}; provenance not recorded")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Import failed: {e}")
    return stats | {"backup": backup}


@router.patch("/contacts/{cid}/eligibility")
def set_elig(cid: int, body: schemas.EligibilityIn, db: Session = Depends(get_db)):
    c = db.get(BusinessContact, cid)
    if not c:
        raise HTTPException(404)
    try:
        contacts_svc.set_eligibility(db, c, body.value, body.basis)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@router.post("/suppressions")
def suppress(body: schemas.SuppressIn, db: Session = Depends(get_db)):
    if not (body.email or body.domain):
        raise HTTPException(422, "Provide email or domain")
    return {"contacts_updated": contacts_svc.add_suppression(db, body.email, body.domain, body.reason)}


# ---------------------------------------------------------------- portfolio / usage / admin
@router.get("/portfolio")
def get_portfolio():
    return load_portfolio()


@router.patch("/portfolio/{pid}")
def toggle_portfolio(pid: str, body: schemas.PortfolioToggle):
    items = load_portfolio()
    for i in items:
        if i["id"] == pid:
            i["verified"] = body.verified
            if body.url is not None:
                i["url"] = body.url
            save_portfolio(items)
            return i
    raise HTTPException(404)


@router.post("/opportunities/rescore")
def rescore(db: Session = Depends(get_db)):
    """Recompute scores after portfolio verification changes."""
    pf = load_portfolio()
    n = 0
    for o in db.scalars(select(Opportunity)):
        raw = RawOpportunity(source_key=o.source_key, url=o.original_url, title=o.title, company_name=o.company_name,
                             company_website=o.company.website if o.company else "", description=o.description,
                             posted_at=o.posted_at, remote_status=o.remote_status,
                             location_requirements=o.location_requirements, budget_min=o.budget_min,
                             budget_max=o.budget_max, currency=o.currency, rate_type=o.rate_type)
        sc = score(raw, None, pf)
        o.fit_score, o.fit_explanation, o.portfolio_evidence = sc["total"], sc["explanation"], sc["portfolio_evidence"]
        o.score_components = {"points": sc["components"], "max": sc["max"], "unknown": sc["unknown"], "coverage": sc["data_coverage"]}
        o.recommended_action = recommend(o.listing_status, sc["total"], sc["geo"], any(e["verified"] for e in sc["portfolio_evidence"]))
        n += 1
    db.commit()
    return {"rescored": n}


@router.get("/usage")
def usage_list(db: Session = Depends(get_db)):
    s = get_settings()
    rows = db.scalars(select(UsageEvent).order_by(UsageEvent.id.desc()).limit(200)).all()
    return {"month_spend_usd": round(usage.month_spend(db), 4), "monthly_budget_usd": s.monthly_budget_usd,
            "llm_price_note": "Prices come from .env and are NOT verified against the provider's current price list.",
            "events": [{"at": _d(e.at), "kind": e.kind, "provider": e.provider, "units": e.units,
                        "cost_usd": e.cost_usd, "estimated": e.estimated, "run_id": e.run_id, "note": e.note} for e in rows]}


@router.post("/admin/backup")
def make_backup():
    try:
        return {"path": str(backup_database())}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
