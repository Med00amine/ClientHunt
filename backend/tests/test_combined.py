import csv
import io
import re
import zipfile

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.config import get_settings
from app.models import BusinessContact, Opportunity, Suppression
from app.services import exporter, runner
from .helpers import FakeAdapter, factory_for, raw
from .test_csv_and_runs import go
from .test_leads import APPLY

SHEETS = ["Summary", "Leads", "Opportunities", "Prospects", "Emails", "Runs"]


def two_runs(db):
    """Run 1 finds A and B; run 2 finds B again and C. B must appear once, seen by runs 1 and 2."""
    a = raw(1, description=APPLY, company_name="Alpha")
    b = raw(2, company_name="Beta")
    c = raw(3, description=APPLY.replace("jobs@", "hello@"), company_name="Gamma")
    r1 = go(db, {"fake": FakeAdapter([a, b])})
    r2 = go(db, {"fake": FakeAdapter([b, c])})
    return r1, r2


def book(db, **kw):
    return load_workbook(io.BytesIO(exporter.build_xlsx(exporter.build_combined(db, **kw))))


def rows_of(ws):
    head = [c.value for c in ws[1]]
    return [dict(zip(head, [c.value for c in r])) for r in ws.iter_rows(min_row=2)]


def test_workbook_has_the_five_sheets_with_exact_headers(db):
    two_runs(db)
    wb = book(db)
    assert wb.sheetnames == SHEETS
    assert [c.value for c in wb["Leads"][1]] == exporter.LEAD_COLUMNS
    assert [c.value for c in wb["Opportunities"][1]] == exporter.COMBINED_OPP_COLUMNS
    assert [c.value for c in wb["Prospects"][1]] == exporter.PROSPECT_COLUMNS
    assert [c.value for c in wb["Emails"][1]] == exporter.EMAIL_COLUMNS
    assert [c.value for c in wb["Runs"][1]] == exporter.RUN_COLUMNS


def test_opportunities_are_deduplicated_across_runs_and_list_the_runs(db):
    r1, r2 = two_runs(db)
    opps = rows_of(book(db)["Opportunities"])
    assert len(opps) == 3                                                    # A, B, C once each (B was in both runs)
    by = {o["company_name"]: o for o in opps}
    assert by["Beta"]["runs_seen"] == f"{r1.id}, {r2.id}" and by["Alpha"]["runs_seen"] == str(r1.id) and by["Gamma"]["runs_seen"] == str(r2.id)
    runs = rows_of(book(db)["Runs"])
    assert [r["run_id"] for r in runs] == [r1.id, r2.id] and all(r["status"] == "completed" for r in runs)


def test_values_match_the_database(db):
    two_runs(db)
    for row in rows_of(book(db)["Opportunities"]):
        o = db.get(Opportunity, row["opportunity_id"])
        assert row["original_url"] == o.original_url and row["title"] == o.title
        assert row["fit_score"] == o.fit_score and row["hiring_ease_score"] == o.ease_score
        assert row["source_platform"] == o.source_key and row["engagement_type"] == o.engagement_type
        assert (row["description"] or "") == o.description


def test_leads_sheet_one_row_per_email_with_source_and_sorted(db):
    two_runs(db)
    leads = rows_of(book(db)["Leads"])
    assert {l["business_email"] for l in leads} == {"jobs@acme.example", "hello@acme.example"}
    assert [l["rank"] for l in leads] == list(range(1, len(leads) + 1))
    for l in leads:
        assert l["email_source_url"].startswith("https://") and l["email_found_at"] is not None
        assert l["email_eligibility"] == "eligible" and l["listing_url"] and "email to apply" in l["why_it_looks_easy"]
    assert len(rows_of(book(db)["Emails"])) == 2


def test_summary_counts_are_correct_and_not_misleading(db):
    two_runs(db)
    ws = book(db)["Summary"]
    cells = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(3, ws.max_row + 1)}
    assert cells["Runs included"] == 2
    assert cells["Opportunities (each listed once, even if several runs found it)"] == 3
    assert cells["Leads (opportunities with a published email that fit you and are open to Tunisia)"] == 2
    assert cells["Emails (company-published, each with its source link)"] == 2
    assert "Freelancer.com" in cells["Not included"]


def test_leads_sheet_only_lists_actionable_leads_but_nothing_is_lost(db):
    good = raw(1, description=APPLY, company_name="Good Co")
    restricted = raw(2, description=APPLY.replace("jobs@", "us@"), company_name="UK Co", location_requirements="UK")
    weak = raw(3, title="Sales role", description="Python. To apply, email your resume to sales@weak.example. " * 3, company_name="Weak Co")
    go(db, {"fake": FakeAdapter([good, restricted, weak])})
    wb = book(db)
    leads = rows_of(wb["Leads"])
    assert {l["company_name"] for l in leads} == {"Good Co"}                       # fit >= 35 and not restricted
    assert all(l["location_check"] in ("worldwide", "compatible", "unknown") and l["fit_score"] >= exporter.LEAD_MIN_FIT for l in leads)
    opps = {o["company_name"]: o for o in rows_of(wb["Opportunities"])}
    assert opps["UK Co"]["location_check"] == "restricted" and opps["Good Co"]["location_check"] == "worldwide"
    assert set(opps) == {"Good Co", "UK Co", "Weak Co"}                            # the full list keeps everything
    assert {e["business_email"] for e in rows_of(wb["Emails"])} == {"jobs@acme.example", "us@acme.example", "sales@weak.example"}
    ws = wb["Summary"]
    cells = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(3, ws.max_row + 1)}
    assert cells["Leads (opportunities with a published email that fit you and are open to Tunisia)"] == 1
    assert "location_check" in cells and "fit >= 35" in cells["How to read it"]


def test_excluded_and_suppressed_are_left_out(db):
    two_runs(db)
    beta = db.scalar(select(Opportunity).where(Opportunity.company_name == "Beta"))
    beta.review_status = "excluded"
    db.add(Suppression(email_norm="hello@acme.example", reason="opt-out"))
    for c in db.scalars(select(BusinessContact)):
        if c.email_norm == "hello@acme.example":
            c.suppressed, c.outreach_eligibility = True, "not_eligible"
    db.commit()
    wb = book(db)
    assert {o["company_name"] for o in rows_of(wb["Opportunities"])} == {"Alpha", "Gamma"}
    assert {l["business_email"] for l in rows_of(wb["Leads"])} == {"jobs@acme.example"}
    assert {e["business_email"] for e in rows_of(wb["Emails"])} == {"jobs@acme.example"}
    assert "Beta" in {o["company_name"] for o in rows_of(book(db, include_excluded=True)["Opportunities"])}


def test_text_is_never_a_formula_in_the_workbook(db, tmp_path):
    go(db, {"fake": FakeAdapter([raw(1, title="=cmd|' /C calc'!A0", company_name="+SUM(1)", description=APPLY + " @evil -2+3")])})
    data = exporter.build_xlsx(exporter.build_combined(db))
    ws = load_workbook(io.BytesIO(data))["Opportunities"]
    row = rows_of(ws)[0]
    assert row["title"] == "=cmd|' /C calc'!A0" and row["company_name"] == "+SUM(1)"      # text preserved exactly
    t = [c for c in ws[2] if c.value == "=cmd|' /C calc'!A0"][0]
    assert t.data_type == "s"
    z = zipfile.ZipFile(io.BytesIO(data))
    for name in z.namelist():
        if name.startswith("xl/worksheets/"):
            assert "<f>" not in z.read(name).decode() and "<f " not in z.read(name).decode()   # no formula element anywhere


def test_only_http_links_are_clickable(db):
    go(db, {"fake": FakeAdapter([raw(1, description=APPLY, company_name="Bad"), raw(2, description=APPLY, url="https://ok.example/jobs/2", company_name="Good")])})
    bad = db.scalar(select(Opportunity).where(Opportunity.company_name == "Bad"))
    bad.original_url = "javascript:alert(1)"          # defence in depth: even if one ever got stored
    db.commit()
    ws = book(db)["Opportunities"]
    cols = {c.value: c.column for c in ws[1]}
    links = {r[cols["company_name"] - 1].value: r[cols["original_url"] - 1].hyperlink for r in ws.iter_rows(min_row=2)}
    assert links["Good"] is not None and links["Good"].target == "https://ok.example/jobs/2"
    assert links["Bad"] is None                       # shown as text, never a link


def test_odd_text_does_not_break_the_file(db):
    go(db, {"fake": FakeAdapter([raw(1, title="Ctrl\x00char\x0b title", description="x" * 40000 + APPLY, company_name="Big")])})
    row = rows_of(book(db)["Opportunities"])[0]
    assert row["title"] == "Ctrlchar title" and len(row["description"]) <= 32000


def test_single_csv_is_one_row_per_opportunity_with_emails_joined(db):
    two_runs(db)
    body = exporter.build_combined_csv(exporter.build_combined(db))
    assert body.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline="")))
    assert len(rows) == 3 and list(rows[0].keys()) == exporter.COMBINED_OPP_COLUMNS
    by = {r["company_name"]: r for r in rows}
    assert by["Alpha"]["business_emails"] == "jobs@acme.example" and by["Beta"]["business_emails"] == ""
    assert by["Beta"]["runs_seen"].count(",") == 1


def test_single_csv_neutralises_formulas(db):
    go(db, {"fake": FakeAdapter([raw(1, title="=HYPERLINK(\"http://evil\")", description=APPLY)])})
    rows = list(csv.DictReader(io.StringIO(exporter.build_combined_csv(exporter.build_combined(db)).decode("utf-8-sig"), newline="")))
    assert rows[0]["title"].startswith("'=")


def test_empty_database_gives_empty_but_valid_tables(db):
    d = exporter.build_combined(db)
    assert d["counts"] == {"runs": 0, "opportunities": 0, "leads": 0, "emails": 0, "prospects": 0}
    assert load_workbook(io.BytesIO(exporter.build_xlsx(d))).sheetnames == SHEETS


# ---------------------------------------------------------------- API
def test_api_downloads_xlsx_and_csv_and_adds_no_files(client, db):
    two_runs(db)
    before = sorted(p.name for p in get_settings().exports_dir.glob("*"))
    r = client.get("/api/export/all")
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    assert re.search(r'filename="clienthunt_all_runs_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.xlsx"', r.headers["content-disposition"])
    assert r.headers["cache-control"] == "no-store" and "opportunities=3" in r.headers["x-counts"]
    assert load_workbook(io.BytesIO(r.content)).sheetnames == SHEETS
    c = client.get("/api/export/all?format=csv")
    assert c.status_code == 200 and c.headers["content-type"].startswith("text/csv") and c.headers["content-disposition"].endswith('.csv"')
    assert sorted(p.name for p in get_settings().exports_dir.glob("*")) == before        # on demand: no extra files
    assert client.get("/api/export/all/counts").json() == {"runs": 2, "opportunities": 3, "leads": 2, "emails": 2, "prospects": 0}


def test_api_validation_empty_and_auth(client, db, monkeypatch):
    assert client.get("/api/export/all").status_code == 404
    assert client.get("/api/export/all?format=pdf").status_code == 422
    two_runs(db)
    assert client.get("/api/export/all?include_excluded=true").status_code == 200
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/export/all").status_code == 401
    assert client.get("/api/export/all/counts").status_code == 401


def test_opportunities_open_to_tunisia_come_first_and_summary_counts_locations(db):
    uk = raw(1, description=APPLY, company_name="UK Co", location_requirements="UK")
    ww = raw(2, description="Python FastAPI AWS Docker LLM RAG " * 8, company_name="World Co", location_requirements="Worldwide")
    unk = raw(3, description="Python FastAPI AWS Docker LLM RAG " * 8, company_name="Unknown Co", location_requirements="")
    go(db, {"fake": FakeAdapter([uk, unk, ww])})
    wb = book(db)
    assert [o["company_name"] for o in rows_of(wb["Opportunities"])][-1] == "UK Co"           # restricted last
    assert rows_of(wb["Opportunities"])[0]["location_check"] in ("worldwide", "compatible")
    ws = wb["Summary"]
    cells = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(3, ws.max_row + 1)}
    assert "worldwide: 1" in cells["By location check"] and "restricted: 1" in cells["By location check"]
