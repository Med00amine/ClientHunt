"""Persistent run engine. A run is a DB row; the worker thread executes pending runs.
Fetches are read-only GETs so a run interrupted by a restart is safely re-executed (upserts are idempotent)."""
from __future__ import annotations

import threading
import time
import traceback
from datetime import timedelta
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import adapters
from ..adapters.base import AdapterError, AdapterUnavailable
from ..config import get_settings
from ..models import (Company, Opportunity, ResearchRun, RunOpportunity, SearchProfile, Source, utcnow)
from ..types import SearchParams
from . import drafting, exporter, pipeline, research, usage
from .safefetch import SafeFetcher

AdapterFactory = Callable[[str, Session], "adapters.Adapter"]


def default_factory(key: str, db: Session):
    return adapters.registry[key](db)


def create_run(db: Session, params: dict, profile_id: int | None = None, retry_of: ResearchRun | None = None) -> ResearchRun:
    s = get_settings()
    p = dict(params or {})
    p["max_results"] = min(int(p.get("max_results", 100)), s.max_results_per_source)
    p.setdefault("max_budget_usd", s.default_run_budget_usd)
    prof = db.get(SearchProfile, profile_id) if profile_id else None
    run = ResearchRun(profile_id=profile_id, profile_name=prof.name if prof else p.get("name", "Ad-hoc search"),
                      params=p, status="pending", retry_count=(retry_of.retry_count + 1) if retry_of else 0)
    db.add(run)
    db.commit()
    return run


def recover_after_restart(db: Session) -> int:
    """Runs left 'running' by a crash/restart go back to pending (idempotent re-execution)."""
    n = 0
    for r in db.scalars(select(ResearchRun).where(ResearchRun.status == "running")):
        r.status, r.retry_count = "pending", r.retry_count + 1
        r.errors = (r.errors or []) + ["Interrupted by application restart; re-queued"]
        n += 1
    db.commit()
    return n


def cancel_run(db: Session, run: ResearchRun) -> None:
    if run.status == "pending":
        run.status, run.finished_at = "cancelled", utcnow()
    elif run.status == "running":
        run.cancel_requested = True
    db.commit()


def _cancelled(db: Session, run: ResearchRun) -> bool:
    db.refresh(run)
    return run.cancel_requested


def execute_run(db: Session, run_id: int, factory: AdapterFactory = default_factory,
                fetcher: SafeFetcher | None = None) -> ResearchRun:
    s = get_settings()
    run = db.get(ResearchRun, run_id)
    if run.status not in ("pending", "running"):
        return run
    run.status, run.started_at, run.finished_at = "running", utcnow(), None
    run.cancel_requested = False
    db.execute(delete(RunOpportunity).where(RunOpportunity.run_id == run.id))
    run.discovered = run.stored = run.new_count = run.rejected_duplicate = run.rejected_irrelevant = 0
    run.source_results, run.incomplete_notes = {}, []
    db.commit()
    p = SearchParams.from_dict(run.params)
    if not p.sources:
        p.sources = [x.key for x in db.scalars(select(Source).where(Source.enabled.is_(True), Source.kind == "api"))]
    run.sources_queried = list(p.sources)
    run.info_notes = []
    db.commit()
    errors: list[str] = list(run.errors or [])
    all_raws = []
    ok_sources = failed = unavailable = 0
    cancelled = False
    try:
        for key in p.sources:
            if _cancelled(db, run):
                cancelled = True
                break
            run.current_source = key
            db.commit()
            try:
                raws = factory(key, db).fetch(p)
                # provider-side fetch counts are capped per source
                raws = raws[: max(p.max_results * 3, p.max_results)]
                run.source_results = {**run.source_results, key: {"status": "ok", "fetched": len(raws)}}
                ok_sources += 1
                all_raws.extend(raws)
            except AdapterUnavailable as e:
                run.source_results = {**run.source_results, key: {"status": "unavailable", "error": str(e)}}
                run.incomplete_notes = run.incomplete_notes + [f"{key}: {e}"]
                unavailable += 1
            except (AdapterError, Exception) as e:  # noqa: BLE001
                msg = f"{key}: {type(e).__name__}: {e}"[:300]
                errors.append(msg)
                run.source_results = {**run.source_results, key: {"status": "failed", "error": msg}}
                failed += 1
            db.commit()
        if not cancelled and _cancelled(db, run):
            cancelled = True
        if not cancelled:
            stats = pipeline.process(db, all_raws, p, run.id)
            run.discovered, run.stored = stats["discovered"], stats["stored"]
            run.new_count, run.rejected_irrelevant = stats["new"], stats["rejected_irrelevant"]
            run.rejected_duplicate = stats["rejected_duplicate"]
            run.selected_for_review = sum(1 for oid in stats["ids"]
                                          if (db.get(Opportunity, oid).fit_score >= 40))
            _enrich(db, run, p, stats["ids"], fetcher)
    except Exception as e:  # noqa: BLE001
        errors.append(f"run error: {type(e).__name__}: {e}")
        run.last_error = traceback.format_exc()[-500:]
        failed += 1
        db.rollback()
        run = db.get(ResearchRun, run_id)
    run.errors = errors
    run.last_error = errors[-1] if errors else run.last_error
    run.current_source = ""
    run.finished_at = utcnow()
    run.cost_usd = usage.run_spend(db, run.id)
    if cancelled:
        run.status = "cancelled"
    elif ok_sources == 0:
        run.status = "failed"
        if not errors:
            errors.append("No source could be queried"); run.errors = errors
    elif failed or unavailable or run.incomplete_notes:
        run.status = "partial"
    else:
        run.status = "completed"
    if run.status in ("completed", "partial"):
        # Automatic CSV (also with zero rows). The final status is committed together with the export record,
        # so observers never see "completed" without its export.
        exporter.export_run_bundle(db, run)
    else:
        db.commit()
    return run


def _enrich(db: Session, run: ResearchRun, p: SearchParams, ids: list[int], fetcher: SafeFetcher | None) -> None:
    s = get_settings()
    opps = sorted((db.get(Opportunity, i) for i in ids), key=lambda o: -o.fit_score)
    opps = [o for o in opps if o.review_status != "excluded"]
    max_c = p.max_companies if p.max_companies is not None else s.max_companies_per_run
    max_d = p.max_drafts if p.max_drafts is not None else s.max_drafts_per_run
    fetcher = fetcher or SafeFetcher()
    done_c = 0
    seen_c = set()
    for o in opps:
        if not (o.company_id and o.fit_score >= 40):
            continue
        c = db.get(Company, o.company_id)
        if c.id in seen_c or not c.website or c.research_status not in ("not_started", "failed"):
            continue
        seen_c.add(c.id)
        if done_c >= max_c:
            run.info_notes = run.info_notes + [f"Company research limited to {max_c} per run (setting); more companies remain unresearched"]
            break
        if _cancelled(db, run):
            return
        research.research_company(db, c, o, fetcher)
        done_c += 1
    run.companies_researched = done_c
    n = 0
    for o in opps:
        if n >= max_d:
            break
        if o.fit_score < 40 or o.proposal_status != "none":
            continue
        if s.llm_enabled:
            remaining, why = usage.budget_remaining(db, run.id, p.max_budget_usd)
            if remaining <= 0:
                run.incomplete_notes = run.incomplete_notes + [f"paid (LLM) drafting stopped: {why} reached; template drafts used"]
        drafting.generate_draft(db, o, run_id=run.id)
        n += 1
    run.drafts_generated = n
    db.commit()


class Worker(threading.Thread):
    def __init__(self, session_factory, factory: AdapterFactory = default_factory, interval: float = 2.0):
        super().__init__(daemon=True, name="run-worker")
        self.session_factory, self.factory, self.interval = session_factory, factory, interval
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                with self.session_factory() as db:
                    nxt = db.scalar(select(ResearchRun).where(ResearchRun.status == "pending")
                                    .order_by(ResearchRun.id).limit(1))
                    if nxt:
                        execute_run(db, nxt.id, self.factory)
                        continue
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()
