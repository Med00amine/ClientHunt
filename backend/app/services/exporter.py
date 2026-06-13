"""CSV export. Files are never overwritten, formula injection is neutralised, UTF-8 with BOM for Excel."""
from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (BusinessContact, Company, Evidence, ExportRecord, Opportunity, ProposalDraft,
                      ResearchRun, RunOpportunity, utcnow)
from ..textutil import csv_safe

OPP_COLUMNS = [
    "run_id", "discovered_at", "source_platform", "source_type", "opportunity_id", "title", "company_name",
    "company_website", "original_url", "posted_at", "deadline", "engagement_type", "remote_status",
    "location_requirements", "budget_min", "budget_max", "currency", "rate_type", "description",
    "required_skills", "matched_skills", "portfolio_evidence", "fit_score", "fit_explanation",
    "missing_requirements", "company_research_summary", "research_sources", "contact_name", "contact_role",
    "business_email", "contact_source_url", "contact_verified_status", "outreach_eligibility",
    "recommended_action", "proposal_status", "application_status", "last_verified_at",
    "hiring_ease_score", "hiring_signals", "apply_method",
]
EMAIL_COLUMNS = [
    "run_id", "company_name", "company_website", "business_email", "email_type", "contact_purpose",
    "outreach_eligibility", "eligibility_basis", "email_source_url", "email_found_at", "email_context",
    "verified_status", "listing_title", "listing_url", "source_platform", "apply_method", "hiring_ease_score",
    "hiring_signals", "fit_score", "engagement_type", "location_requirements", "posted_at", "opportunity_id",
]
CONTACT_COLUMNS = ["contact_id", "name", "role", "company_name", "business_email", "is_generic_address",
                   "source_type", "source_url", "retrieved_at", "verified_status", "outreach_eligibility",
                   "eligibility_basis"]


def _dt(v: datetime | None) -> str:
    return v.strftime("%Y-%m-%dT%H:%M:%SZ") if v else ""


def _pick_contact(db: Session, opp: Opportunity) -> BusinessContact | None:
    """Only contacts with recorded provenance and not suppressed: the one tied to this listing first
    (careers/application addresses before general ones), else one for the same company."""
    base = select(BusinessContact).where(BusinessContact.source_url != "", BusinessContact.suppressed.is_(False),
                                         BusinessContact.outreach_eligibility != "not_eligible")
    rank = (BusinessContact.outreach_eligibility != "eligible", BusinessContact.id)
    c = db.scalar(base.where(BusinessContact.opportunity_id == opp.id).order_by(*rank).limit(1))
    if c is None and opp.company_id:
        c = db.scalar(base.where(BusinessContact.company_id == opp.company_id).order_by(*rank).limit(1))
    return c


def opportunity_rows(db: Session, run_id: int) -> list[dict]:
    links = db.scalars(select(RunOpportunity).where(RunOpportunity.run_id == run_id)
                       .order_by(RunOpportunity.id)).all()
    rows, seen = [], set()
    for link in links:
        if link.opportunity_id in seen:
            continue
        seen.add(link.opportunity_id)
        o = db.get(Opportunity, link.opportunity_id)
        company = db.get(Company, o.company_id) if o.company_id else None
        facts = []
        if company:
            facts = db.scalars(select(Evidence).where(Evidence.company_id == company.id,
                                                      Evidence.kind == "fact")).all()
        c = _pick_contact(db, o)
        elig = "unknown"
        if c:
            elig = c.outreach_eligibility if c.outreach_eligibility in ("eligible", "not_eligible") else "review_required"
        draft = db.scalar(select(ProposalDraft).where(ProposalDraft.opportunity_id == o.id)
                          .order_by(ProposalDraft.id.desc()).limit(1))
        score = o.score_override if o.score_override is not None else o.fit_score
        rows.append({
            "run_id": run_id, "discovered_at": _dt(link.discovered_at), "source_platform": o.source_key,
            "source_type": o.source_type, "opportunity_id": o.id, "title": o.title,
            "company_name": o.company_name, "company_website": company.website if company else "",
            "original_url": o.original_url, "posted_at": _dt(o.posted_at), "deadline": _dt(o.deadline),
            "engagement_type": o.engagement_type, "remote_status": o.remote_status,
            "location_requirements": o.location_requirements,
            "budget_min": "" if o.budget_min is None else o.budget_min,
            "budget_max": "" if o.budget_max is None else o.budget_max,
            "currency": o.currency, "rate_type": o.rate_type, "description": o.description,
            "required_skills": "; ".join(o.required_skills or []),
            "matched_skills": "; ".join(o.matched_skills or []),
            "portfolio_evidence": "; ".join(e["title"] for e in (o.portfolio_evidence or []) if e.get("verified")),
            "fit_score": score, "fit_explanation": o.fit_explanation,
            "missing_requirements": "; ".join(o.missing_requirements or []),
            "company_research_summary": " | ".join(f.claim for f in facts[:5]),
            "research_sources": "; ".join(sorted({f.source_url for f in facts if f.source_url})),
            "contact_name": c.name if c else "", "contact_role": c.role if c else "",
            "business_email": c.email if c else "", "contact_source_url": c.source_url if c else "",
            "contact_verified_status": c.verified_status if c else "", "outreach_eligibility": elig,
            "recommended_action": o.recommended_action, "proposal_status": o.proposal_status or ("draft" if draft else "none"),
            "application_status": o.application_status, "last_verified_at": _dt(o.last_verified_at),
            "hiring_ease_score": o.ease_score, "hiring_signals": "; ".join(o.ease_signals or []),
            "apply_method": o.apply_method,
        })
    return rows


def _write_unique(directory: Path, prefix: str, columns: list[str], rows: list[dict]) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    n = 0
    while True:
        name = f"{prefix}_{stamp}{'' if n == 0 else f'_{n + 1}'}.csv"
        path = directory / name
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)  # never overwrite
            break
        except FileExistsError:
            n += 1
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            for r in rows:
                w.writerow({k: csv_safe(r.get(k, "")) for k in columns})
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        path.unlink(missing_ok=True)  # no partial file left behind
        raise
    return path, digest


def export_run(db: Session, run: ResearchRun, commit: bool = True) -> ExportRecord:
    """Create the opportunity CSV for a run and record it. On failure a failed record is stored."""
    s = get_settings()
    try:
        rows = opportunity_rows(db, run.id)
        path, digest = _write_unique(s.exports_dir, "opportunities", OPP_COLUMNS, rows)
        rec = ExportRecord(run_id=run.id, kind="opportunities", filename=path.name, path=str(path),
                           row_count=len(rows), sha256=digest, status="ok", run_status=run.status)
        run.export_status = "ok"
    except Exception as e:  # noqa: BLE001
        rec = ExportRecord(run_id=run.id, kind="opportunities", status="failed", error=str(e)[:500],
                           run_status=run.status)
        run.export_status = "failed"
    db.add(rec)
    if commit:
        db.commit()
    return rec


def export_contacts(db: Session) -> ExportRecord:
    """Optional contacts CSV: only eligible, non-suppressed contacts that have recorded provenance."""
    s = get_settings()
    try:
        contacts = db.scalars(select(BusinessContact).where(
            BusinessContact.outreach_eligibility == "eligible", BusinessContact.suppressed.is_(False),
            BusinessContact.source_url != "")).all()
        rows = [{"contact_id": c.id, "name": c.name, "role": c.role, "company_name": c.company_name,
                 "business_email": c.email, "is_generic_address": c.is_generic, "source_type": c.source_type,
                 "source_url": c.source_url, "retrieved_at": _dt(c.retrieved_at),
                 "verified_status": c.verified_status, "outreach_eligibility": c.outreach_eligibility,
                 "eligibility_basis": c.eligibility_basis} for c in contacts]
        path, digest = _write_unique(s.exports_dir, "contacts", CONTACT_COLUMNS, rows)
        rec = ExportRecord(kind="contacts", filename=path.name, path=str(path), row_count=len(rows),
                           sha256=digest, status="ok")
    except Exception as e:  # noqa: BLE001
        rec = ExportRecord(kind="contacts", status="failed", error=str(e)[:500])
    db.add(rec)
    db.commit()
    return rec


def _email_rows(db: Session, contacts: list[BusinessContact], run_id: int | str = "") -> list[dict]:
    rows = []
    for c in contacts:
        o = db.get(Opportunity, c.opportunity_id) if c.opportunity_id else None
        company = db.get(Company, c.company_id) if c.company_id else (db.get(Company, o.company_id) if o and o.company_id else None)
        rows.append({
            "run_id": run_id, "company_name": c.company_name or (o.company_name if o else ""),
            "company_website": company.website if company else "", "business_email": c.email,
            "email_type": "role / generic mailbox" if c.is_generic else "individual address (as published)",
            "contact_purpose": c.contact_purpose, "outreach_eligibility": c.outreach_eligibility,
            "eligibility_basis": c.eligibility_basis, "email_source_url": c.source_url,
            "email_found_at": _dt(c.retrieved_at), "email_context": c.source_note,
            "verified_status": c.verified_status, "listing_title": o.title if o else "",
            "listing_url": o.original_url if o else "", "source_platform": o.source_key if o else "",
            "apply_method": o.apply_method if o else "", "hiring_ease_score": o.ease_score if o else "",
            "hiring_signals": "; ".join(o.ease_signals or []) if o else "",
            "fit_score": (o.score_override if o.score_override is not None else o.fit_score) if o else "",
            "engagement_type": o.engagement_type if o else "", "location_requirements": o.location_requirements if o else "",
            "posted_at": _dt(o.posted_at) if o else "", "opportunity_id": o.id if o else "",
        })
    rows.sort(key=lambda r: (r["outreach_eligibility"] != "eligible", -(r["hiring_ease_score"] or 0 if r["hiring_ease_score"] != "" else 0)))
    return rows


def _usable_contacts(stmt):
    return stmt.where(BusinessContact.source_url != "", BusinessContact.suppressed.is_(False),
                      BusinessContact.outreach_eligibility != "not_eligible")


def run_emails(db: Session, run_id: int) -> list[BusinessContact]:
    opp_ids = select(RunOpportunity.opportunity_id).where(RunOpportunity.run_id == run_id)
    return list(db.scalars(_usable_contacts(select(BusinessContact).where(BusinessContact.opportunity_id.in_(opp_ids)))
                           .order_by(BusinessContact.id)).all())


def export_run_emails(db: Session, run: ResearchRun, commit: bool = True) -> ExportRecord:
    """Emails CSV for a run: only addresses the company published (with source URL and date)."""
    s = get_settings()
    try:
        rows = _email_rows(db, run_emails(db, run.id), run.id)
        path, digest = _write_unique(s.exports_dir, "emails", EMAIL_COLUMNS, rows)
        rec = ExportRecord(run_id=run.id, kind="emails", filename=path.name, path=str(path), row_count=len(rows),
                           sha256=digest, status="ok", run_status=run.status)
    except Exception as e:  # noqa: BLE001
        rec = ExportRecord(run_id=run.id, kind="emails", status="failed", error=str(e)[:500], run_status=run.status)
        run.export_status = "failed"
    db.add(rec)
    if commit:
        db.commit()
    return rec


def export_run_bundle(db: Session, run: ResearchRun) -> tuple[ExportRecord, ExportRecord]:
    """Opportunities CSV + emails CSV, committed together with the run's final status."""
    a = export_run(db, run, commit=False)
    b = export_run_emails(db, run, commit=False)
    db.commit()
    return a, b


def export_all_emails(db: Session) -> ExportRecord:
    """Every stored address that has a source URL, is not suppressed and not marked not_eligible."""
    s = get_settings()
    try:
        contacts = db.scalars(_usable_contacts(select(BusinessContact)).order_by(BusinessContact.id)).all()
        rows = _email_rows(db, list(contacts))
        path, digest = _write_unique(s.exports_dir, "emails_all", EMAIL_COLUMNS, rows)
        rec = ExportRecord(kind="emails", filename=path.name, path=str(path), row_count=len(rows), sha256=digest, status="ok")
    except Exception as e:  # noqa: BLE001
        rec = ExportRecord(kind="emails", status="failed", error=str(e)[:500])
    db.add(rec)
    db.commit()
    return rec
