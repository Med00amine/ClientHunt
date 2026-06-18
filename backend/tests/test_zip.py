import csv
import io
import zipfile

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ExportRecord
from app.services import runner
from .helpers import FakeAdapter, factory_for, raw
from .test_leads import APPLY


def make_runs(client, db, n=2):
    ids = []
    for i in range(n):
        body = {"search": {"name": f"t{i}", "min_fit": 0, "remote_only": False, "posted_within_days": None,
                           "sources": ["fake"], "max_companies": 0, "max_drafts": 0}}
        rid = client.post("/api/runs", json=body).json()["id"]
        runner.execute_run(db, rid, factory_for({"fake": FakeAdapter([raw(i + 1, description=APPLY)])}))
        ids.append(rid)
    return ids


def open_zip(resp):
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"] and ".zip" in resp.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(resp.content))


def test_zip_contains_every_csv_identical_to_disk_plus_manifest(client, db):
    ids = make_runs(client, db, 2)
    client.post("/api/exports/emails")  # also an "all emails" export
    z = open_zip(client.get("/api/exports/download-all"))
    recs = db.scalars(select(ExportRecord).where(ExportRecord.status == "ok")).all()
    assert len(recs) == 5  # 2 runs x (opportunities + emails) + all-emails
    names = set(z.namelist())
    assert "manifest.csv" in names and len(names) == 6
    for r in recs:
        assert z.read(f"{r.kind}/{r.filename}") == open(r.path, "rb").read()
    manifest = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode("utf-8-sig"))))
    assert len(manifest) == 5 and all(m["included"] == "yes" for m in manifest)
    assert {m["run_id"] for m in manifest} >= {str(i) for i in ids}


def test_zip_filters_by_kind_and_run(client, db):
    a, b = make_runs(client, db, 2)
    kinds = {n.split("/")[0] for n in open_zip(client.get("/api/exports/download-all?kind=emails")).namelist() if "/" in n}
    assert kinds == {"emails"}
    z = open_zip(client.get(f"/api/exports/download-all?run_id={a}"))
    files = [n for n in z.namelist() if n != "manifest.csv"]
    assert len(files) == 2 and all(f"{a}" == m["run_id"] for m in
                                   csv.DictReader(io.StringIO(z.read("manifest.csv").decode("utf-8-sig"))))
    assert client.get("/api/exports/download-all?kind=bogus").status_code == 422


def test_zip_skips_modified_or_missing_files_and_says_so(client, db):
    make_runs(client, db, 1)
    opp = db.scalars(select(ExportRecord).where(ExportRecord.kind == "opportunities")).first()
    (get_settings().exports_dir / opp.filename).write_text("tampered")
    z = open_zip(client.get("/api/exports/download-all"))
    assert f"opportunities/{opp.filename}" not in z.namelist()
    manifest = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode("utf-8-sig"))))
    bad = [m for m in manifest if m["included"] == "no"]
    assert len(bad) == 1 and "modified" in bad[0]["note"]
    for r in db.scalars(select(ExportRecord)):
        (get_settings().exports_dir / r.filename).unlink(missing_ok=True)
    assert client.get("/api/exports/download-all").status_code == 409


def test_zip_404_when_nothing_exported_and_failed_exports_excluded(client, db):
    assert client.get("/api/exports/download-all").status_code == 404
    db.add(ExportRecord(kind="opportunities", status="failed", error="disk full")); db.commit()
    assert client.get("/api/exports/download-all").status_code == 404


def test_zip_requires_auth_and_leaves_no_temp_files(client, db, monkeypatch):
    make_runs(client, db, 1)
    import glob, tempfile, os
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.zip")))
    assert client.get("/api/exports/download-all").status_code == 200
    assert set(glob.glob(os.path.join(tempfile.gettempdir(), "*.zip"))) == before   # temp file removed after sending
    monkeypatch.setattr(get_settings(), "app_password", "s3cret")
    assert client.get("/api/exports/download-all").status_code == 401


def test_zip_csv_text_unchanged_by_zipping(client, db):
    make_runs(client, db, 1)
    z = open_zip(client.get("/api/exports/download-all?kind=opportunities"))
    name = [n for n in z.namelist() if n.startswith("opportunities/")][0]
    assert z.read(name).startswith(b"\xef\xbb\xbf")     # BOM kept for Excel
