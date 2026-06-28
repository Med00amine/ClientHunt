import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import api, api_prospects, api_strategy, models  # noqa: F401
from .config import get_settings
from .db import SessionLocal, engine
from .services import leads, presets, prospects, rescoring, runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    s.exports_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        presets.seed(db)
        for step in (leads.purge_job_seeker_posts,   # people advertising themselves are not clients
                     leads.close_stale_posts,        # a post edited to say "CLOSED" is not a lead
                     leads.reclassify_contacts,      # drop addresses older, looser rules mistook for application addresses
                     rescoring.refresh_hn_locations,  # re-derive locations of older Hacker News rows with the current parser
                     rescoring.rescore_all,
                     leads.refresh_ease,
                     prospects.reset_stuck):
            try:
                step(db)
            except Exception:  # noqa: BLE001 - a clean-up problem must never stop the app from starting
                db.rollback()
                logging.getLogger("clienthunt").exception("startup clean-up step %s failed", step.__name__)
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
    app.include_router(api_prospects.router)
    app.include_router(api_strategy.router)
    dist = get_settings().frontend_dist
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = dist / path
            return FileResponse(f if path and f.is_file() and f.resolve().is_relative_to(dist.resolve()) else dist / "index.html")
    return app


app = create_app()
