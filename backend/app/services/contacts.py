"""Business contacts live in their own tables. Importing a file never makes anyone eligible for outreach."""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BusinessContact, Suppression, utcnow

_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
GENERIC = {"info", "contact", "hello", "support", "sales", "admin", "office", "team", "hi", "mail", "enquiries"}
HEADER_ALIASES = {"email": {"email", "e-mail", "mail", "email_address"}, "name": {"name", "full_name", "contact"},
                  "company": {"company", "organisation", "organization", "company_name"}}


def map_columns(headers: list[str]) -> dict[str, int]:
    m = {}
    for i, h in enumerate(headers):
        k = (h or "").strip().lower()
        for field, names in HEADER_ALIASES.items():
            if k in names and field not in m:
                m[field] = i
    return m


def is_suppressed(db: Session, email_norm: str) -> bool:
    domain = email_norm.split("@")[-1]
    return db.scalar(select(Suppression.id).where(
        (Suppression.email_norm == email_norm) | (Suppression.domain == domain)).limit(1)) is not None


def import_contacts_file(db: Session, path: Path, source_note: str = "") -> dict:
    """Read-only access to the file. Rows get outreach_eligibility='unknown' and no source_url (provenance missing)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    headers = [str(h or "") for h in next(rows)]
    cols = map_columns(headers)
    if "email" not in cols:
        raise ValueError(f"No email column found in headers: {headers}")
    existing = set(db.scalars(select(BusinessContact.email_norm)).all())
    suppressed_e = {s.email_norm for s in db.scalars(select(Suppression)).all() if s.email_norm}
    suppressed_d = {s.domain for s in db.scalars(select(Suppression)).all() if s.domain}
    stats = {"rows": 0, "imported": 0, "duplicates": 0, "invalid": 0, "suppressed": 0}
    batch = []
    for r in rows:
        stats["rows"] += 1
        email = str(r[cols["email"]] or "").strip()
        norm = email.lower()
        if not _EMAIL.match(norm):
            stats["invalid"] += 1
            continue
        if norm in existing:
            stats["duplicates"] += 1
            continue
        existing.add(norm)
        domain = norm.split("@")[1]
        sup = norm in suppressed_e or domain in suppressed_d
        stats["suppressed"] += int(sup)
        batch.append(BusinessContact(
            email=email, email_norm=norm, domain=domain,
            name=str(r[cols["name"]] or "")[:300] if "name" in cols else "",
            company_name=str(r[cols["company"]] or "")[:300] if "company" in cols else "",
            is_generic=norm.split("@")[0] in GENERIC, source_type="imported_file", source_url="",
            source_note=(source_note or f"Imported from {path.name}; original provenance not recorded")[:500],
            retrieved_at=None, verified_status="unverified", outreach_eligibility="unknown",
            suppressed=sup, created_at=utcnow()))
        stats["imported"] += 1
        if len(batch) >= 2000:
            db.add_all(batch)
            db.commit()
            batch = []
    db.add_all(batch)
    db.commit()
    wb.close()
    return stats


def add_suppression(db: Session, email: str = "", domain: str = "", reason: str = "") -> int:
    norm = email.strip().lower()
    dom = domain.strip().lower() or ""
    db.add(Suppression(email_norm=norm, domain=dom, reason=reason[:300]))
    q = select(BusinessContact)
    q = q.where(BusinessContact.email_norm == norm) if norm else q.where(BusinessContact.domain == dom)
    n = 0
    for c in db.scalars(q):
        c.suppressed, c.outreach_eligibility = True, "not_eligible"
        n += 1
    db.commit()
    return n


def set_eligibility(db: Session, c: BusinessContact, value: str, basis: str) -> None:
    if value not in ("eligible", "review_required", "not_eligible", "unknown"):
        raise ValueError("invalid eligibility")
    if value == "eligible":
        if c.suppressed or is_suppressed(db, c.email_norm):
            raise ValueError("contact is suppressed")
        if not c.source_url:
            raise ValueError("cannot mark eligible without a recorded source URL (provenance)")
        if not basis.strip():
            raise ValueError("record the basis for eligibility (country rule / relationship)")
    c.outreach_eligibility, c.eligibility_basis = value, basis[:500]
    db.commit()
