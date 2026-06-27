import sqlite3
from pathlib import Path

from ..config import get_settings
from ..models import utcnow


def backup_database() -> Path:
    """SQLite online backup into backups/. For PostgreSQL use pg_dump (see the README)."""
    s = get_settings()
    if not s.database_url.startswith("sqlite"):
        raise RuntimeError("Use pg_dump for PostgreSQL backups (see the README)")
    src_path = s.database_url.replace("sqlite:///", "")
    s.backups_dir.mkdir(parents=True, exist_ok=True)
    dest = s.backups_dir / f"clienthunt_{utcnow().strftime('%Y-%m-%d_%H-%M-%S')}.db"
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dest
