import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="clienthunt-test-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}", "EXPORTS_DIR": str(_TMP / "exports"),
    "BACKUPS_DIR": str(_TMP / "backups"), "PORTFOLIO_PATH": str(_TMP / "portfolio.json"),
    "RUN_WORKER_ENABLED": "false", "APP_PASSWORD": "", "SESSION_SECRET": "test-secret",
    "LLM_ENABLED": "false", "ANTHROPIC_API_KEY": "", "FRONTEND_DIST": str(_TMP / "nodist"),
    "MONTHLY_BUDGET_USD": "10",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated():
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean(migrated):
    with engine.begin() as c:
        for t in reversed(Base.metadata.sorted_tables):
            c.execute(t.delete())
    for f in get_settings().exports_dir.glob("*"):
        f.unlink()
    from app.services import presets
    with SessionLocal() as db:
        presets.seed(db)
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
