import csv
import hashlib

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ExportRecord, Opportunity, ResearchRun
from app.services import exporter, runner
from app.textutil import csv_safe
from .helpers import FakeAdapter, factory_for, raw
from app.services.safefetch import SafeFetcher


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def go(db, mapping, sources=None, **params):
    p = {"sources": sources or list(mapping), "min_fit": 0, "remote_only": False, "posted_within_days": None,
         "max_companies": 0, "max_drafts": 0, **params}
    run = runner.create_run(db, p)
    return runner.execute_run(db, run.id, factory_for(mapping))


def test_successful_run_creates_csv_matching_db(db):
    run = go(db, {"fake": FakeAdapter([raw(1), raw(2)])})
    assert run.status == "completed" and run.export_status == "ok"
    rec = db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id))
    rows = read(rec.path)
    assert rec.row_count == len(rows) == 2
    assert list(rows[0].keys()) == exporter.OPP_COLUMNS
    opp = db.scalar(select(Opportunity).where(Opportunity.external_id == "1"))
    row = next(r for r in rows if r["opportunity_id"] == str(opp.id))
    assert row["original_url"] == opp.original_url == "https://example.com/jobs/1"
    assert row["title"] == opp.title and row["run_id"] == str(run.id)
    assert float(row["fit_score"]) == opp.fit_score
    assert rec.filename.startswith("opportunities_") and rec.filename.endswith(".csv")


def test_zero_result_run_creates_header_only_csv(db):
    run = go(db, {"fake": FakeAdapter([])})
    assert run.status == "completed"
    rec = db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id))
    assert rec.row_count == 0
    text = open(rec.path, encoding="utf-8-sig").read().strip().splitlines()
    assert text == [",".join(exporter.OPP_COLUMNS)]


def test_failed_run_records_error_and_no_export(db):
    run = go(db, {"fake": FakeAdapter(error="boom")})
    assert run.status == "failed" and "boom" in run.last_error
    assert run.export_status == "none"
    assert db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id)) is None
    assert list(get_settings().exports_dir.glob("*.csv")) == []


def test_partial_run_is_labelled_partial(db):
    run = go(db, {"fake": FakeAdapter([raw(1)]), "fake2": FakeAdapter(error="down")})
    assert run.status == "partial"
    rec = db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id))
    assert rec.run_status == "partial"


def test_unavailable_source_is_reported_not_faked(db):
    run = go(db, {"fake": FakeAdapter([raw(1)]), "up": FakeAdapter(unavailable="needs approval")})
    assert run.status == "partial"
    assert run.source_results["up"]["status"] == "unavailable"
    assert any("needs approval" in n for n in run.incomplete_notes)


def test_unicode_commas_quotes_newlines_preserved(db):
    desc = 'Café, "résumé"\nnaïve — 日本語, Python FastAPI LLM AWS Docker ' * 5
    run = go(db, {"fake": FakeAdapter([raw(1, description=desc, title="Dev, with comma")])})
    rec = db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id))
    row = read(rec.path)[0]
    assert row["description"] == desc and row["title"] == "Dev, with comma"


def test_duplicates_not_repeated_within_run(db):
    a = raw(1)
    b = raw(1)             # same source id
    c = raw(2, url="https://example.com/jobs/1/")  # same canonical URL, other id
    run = go(db, {"fake": FakeAdapter([a, b, c])})
    rows = read(db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id)).path)
    assert len(rows) == 1
    assert run.rejected_duplicate >= 1 or run.stored == 1


def test_similar_titles_are_not_merged(db):
    run = go(db, {"fake": FakeAdapter([raw(1, title="Python engineer", company_name="X"),
                                       raw(2, title="Python engineer II", company_name="X")])})
    assert run.stored == 2


@pytest.mark.parametrize("bad", ["=HYPERLINK(\"http://evil\",\"x\")", "+1+1", "-2+3", "@SUM(A1)", "\t=1", " =1+1"])
def test_formula_injection_neutralised(bad):
    assert csv_safe(bad).startswith("'")


def test_formula_injection_in_exported_file(db):
    run = go(db, {"fake": FakeAdapter([raw(1, title="=cmd|' /C calc'!A0", company_name="@evil")])})
    row = read(db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id)).path)[0]
    assert row["title"].startswith("'=") and row["company_name"].startswith("'@")


def test_previous_export_never_overwritten(db):
    run = go(db, {"fake": FakeAdapter([raw(1)])})
    first = db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id))
    before = hashlib.sha256(open(first.path, "rb").read()).hexdigest()
    recs = [exporter.export_run(db, run) for _ in range(3)]  # same second -> same stamp
    paths = {first.path, *[r.path for r in recs]}
    assert len(paths) == 4
    assert hashlib.sha256(open(first.path, "rb").read()).hexdigest() == before == first.sha256


def test_export_failure_recorded_and_retryable(db, monkeypatch):
    run = go(db, {"fake": FakeAdapter([raw(1)])})
    monkeypatch.setattr(exporter, "_write_unique", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    rec = exporter.export_run(db, run)
    assert rec.status == "failed" and "disk full" in rec.error and run.export_status == "failed"
    monkeypatch.undo()
    ok = exporter.export_run(db, run)
    assert ok.status == "ok" and run.export_status == "ok"


def test_rows_have_all_columns_and_numeric_budget(db):
    run = go(db, {"fake": FakeAdapter([raw(1, budget_min=40.0, budget_max=60.0, currency="USD", rate_type="hourly")])})
    row = read(db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id)).path)[0]
    assert set(row) == set(exporter.OPP_COLUMNS)
    assert row["budget_min"] == "40.0" and row["currency"] == "USD"
    assert row["business_email"] == "" and row["outreach_eligibility"] == "unknown"


def test_budget_unknown_stays_blank(db):
    run = go(db, {"fake": FakeAdapter([raw(1)])})
    row = read(db.scalar(select(ExportRecord).where(ExportRecord.run_id == run.id)).path)[0]
    assert row["budget_min"] == "" and row["deadline"] == ""


def test_cancel_before_start_and_during(db):
    run = runner.create_run(db, {"sources": ["fake"]})
    runner.cancel_run(db, run)
    assert run.status == "cancelled"
    run2 = runner.create_run(db, {"sources": ["fake", "b"], "min_fit": 0})
    run2.cancel_requested = True
    db.commit()
    # running run with cancel flag set is observed between sources; execute_run resets flag on start,
    # so emulate cancellation via adapter that requests it
    class Cancelling(FakeAdapter):
        def fetch(self, p):
            r = db.get(ResearchRun, run2.id)
            r.cancel_requested = True
            db.commit()
            return super().fetch(p)
    done = runner.execute_run(db, run2.id, factory_for({"fake": Cancelling([raw(1)]), "b": FakeAdapter([raw(2)])}))
    assert done.status == "cancelled" and done.export_status == "none"


def test_restart_recovery_requeues_and_is_idempotent(db):
    run = runner.create_run(db, {"sources": ["fake"], "min_fit": 0, "remote_only": False, "posted_within_days": None,
                                 "max_companies": 0, "max_drafts": 0})
    run.status = "running"
    db.commit()
    assert runner.recover_after_restart(db) == 1
    db.refresh(run)
    assert run.status == "pending" and run.retry_count == 1
    m = {"fake": FakeAdapter([raw(1)])}
    runner.execute_run(db, run.id, factory_for(m))
    runner.execute_run(db, run.id, factory_for(m))  # no-op: already completed
    assert db.query(Opportunity).count() == 1


def test_rerun_marks_existing_as_not_new_and_keeps_history(db):
    go(db, {"fake": FakeAdapter([raw(1)])})
    r2 = go(db, {"fake": FakeAdapter([raw(1, budget_min=50.0, budget_max=80.0, currency="USD", rate_type="hourly")])})
    assert r2.new_count == 0 and db.query(Opportunity).count() == 1
    from app.models import OpportunityHistory
    assert db.query(OpportunityHistory).count() >= 1


def test_run_stats_selected_and_rejected(db):
    bad = raw(2, title="Sales manager", description="Sell stuff. " * 40)
    run = go(db, {"fake": FakeAdapter([raw(1), bad])}, min_fit=30)
    assert run.discovered == 2 and run.stored == 1 and run.rejected_irrelevant == 1


def test_max_drafts_and_drafts_are_never_applications(db):
    run = go(db, {"fake": FakeAdapter([raw(1), raw(2), raw(3)])}, max_drafts=2)
    assert run.drafts_generated == 2
    assert all(o.application_status == "none" for o in db.query(Opportunity))


def test_status_not_visible_as_finished_before_export_exists(db, monkeypatch):
    from app.db import SessionLocal
    seen = {}
    real = exporter.export_run

    def spy(d, run, **kw):
        with SessionLocal() as other:  # what the UI would read mid-export
            seen["status"] = other.get(ResearchRun, run.id).status
        return real(d, run, **kw)
    monkeypatch.setattr(exporter, "export_run", spy)
    run = go(db, {"fake": FakeAdapter([raw(1)])})
    assert seen["status"] == "running" and run.status == "completed"
    assert db.query(ExportRecord).filter_by(run_id=run.id).count() == 2  # opportunities + emails, committed together
