"""Operations CLI:  python -m app.cli {backup|import-contacts PATH|forget EMAIL}"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import delete

from .db import SessionLocal
from .models import BusinessContact
from .services import contacts, presets
from .services.backup import backup_database


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clienthunt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="back up the SQLite database into backups/")
    ic = sub.add_parser("import-contacts", help="import an .xlsx of contacts (read-only; backup is made first)")
    ic.add_argument("path")
    fg = sub.add_parser("forget", help="delete a contact's personal data but keep a suppression entry")
    fg.add_argument("email")
    a = ap.parse_args(argv)
    if a.cmd == "backup":
        print(backup_database())
    elif a.cmd == "import-contacts":
        p = Path(a.path)
        if not p.is_file():
            print(f"not found: {p}", file=sys.stderr)
            return 2
        try:
            print("backup:", backup_database())
        except RuntimeError as e:
            print("backup skipped:", e)
        with SessionLocal() as db:
            presets.seed(db)
            print(contacts.import_contacts_file(db, p))
    elif a.cmd == "forget":
        with SessionLocal() as db:
            contacts.add_suppression(db, email=a.email, reason="erasure request: personal data deleted")
            n = db.execute(delete(BusinessContact).where(BusinessContact.email_norm == a.email.strip().lower())).rowcount
            db.commit()
            print(f"deleted {n} contact row(s); suppression entry kept so the address is never re-imported as eligible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
