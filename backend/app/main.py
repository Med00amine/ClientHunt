from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import api, models  # noqa: F401
from .config import get_settings
from .db import SessionLocal, engine
from .services import presets, runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.exports_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        presets.seed(db)
        runner.recover_after_restart(db)
    worker = None
    if s.run_worker_enabled:
        worker = runner.Worker(SessionLocal)
        worker.start()
    yield
    if worker:
        worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="ClientHunt", lifespan=lifespan)
    app.include_router(api.public)
    app.include_router(api.router)
    dist = get_settings().frontend_dist
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = dist / path
            return FileResponse(f if path and f.is_file() and f.resolve().is_relative_to(dist.resolve()) else dist / "index.html")
    return app


app = create_app()
