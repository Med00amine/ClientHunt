"""Portfolio evidence. Only items the user has verified (verified=true) may be cited in drafts."""
import json
from pathlib import Path

from .config import get_settings

# Facts below come from inspecting the local neurogrid repo (2026-10-26). Items with verified=false
# could not be confirmed from files on this machine; they are never cited until the user flips the flag.
DEFAULT_PORTFOLIO = [
    {
        "id": "neurogrid",
        "title": "Client Acquisition Studio (neurogrid)",
        "url": "https://github.com/Med00amine/neurogrid",
        "verified": True,
        "verified_note": "Local repo inspected: FastAPI + PostgreSQL backend, React UI, persistent job queue, Docker packaging, pytest and Playwright tests.",
        "skills": ["python", "fastapi", "rest api", "postgresql", "docker", "react", "typescript", "testing",
                   "workflow automation", "document processing", "llm"],
        "summary": "A FastAPI + PostgreSQL + React workspace with a persistent background job queue, Docker packaging and automated pytest/Playwright tests; includes optional LLM-assisted research where each extracted fact must match an exact quote from the source page.",
    },
    {
        "id": "rag-project",
        "title": "RAG project",
        "url": "https://github.com/Med00amine/Rag-project",
        "verified": False,
        "verified_note": "Local repo is mostly empty scaffolding (empty Dockerfile/compose). Confirm what actually works before enabling.",
        "skills": ["python", "rag", "llm", "nlp", "fastapi"],
        "summary": "Retrieval-augmented generation project.",
    },
    {
        "id": "churn-api",
        "title": "Customer-churn prediction API",
        "url": "",
        "verified": False,
        "verified_note": "No repository found on this machine. Add the URL and confirm.",
        "skills": ["python", "pytorch", "machine learning", "fastapi", "rest api", "docker"],
        "summary": "Customer-churn prediction served through a REST API.",
    },
    {
        "id": "vocality-soni2",
        "title": "Vocality.ai / Soni2 audiobook pipeline",
        "url": "",
        "verified": False,
        "verified_note": "No repository found on this machine. Add the URL and confirm.",
        "skills": ["python", "document processing", "workflow automation", "aws", "docker"],
        "summary": "Audiobook generation pipeline.",
    },
]


def load_portfolio(path: Path | None = None) -> list[dict]:
    p = path or get_settings().portfolio_path
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return [dict(x) for x in DEFAULT_PORTFOLIO]


def save_portfolio(items: list[dict], path: Path | None = None) -> None:
    p = Path(path or get_settings().portfolio_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, indent=2))
