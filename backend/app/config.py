"""Runtime configuration. Secrets come from the environment / .env only."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{ROOT / 'data' / 'clienthunt.db'}"
    exports_dir: Path = ROOT / "exports"
    backups_dir: Path = ROOT / "backups"
    portfolio_path: Path = ROOT / "data" / "portfolio.json"
    frontend_dist: Path = ROOT / "frontend" / "dist"

    # Authentication. Leave empty only for local development (a warning is shown in the UI).
    app_password: str = ""
    session_secret: str = "dev-only-change-me"
    cookie_secure: bool = False

    # Budget (USD)
    monthly_budget_usd: float = 10.0
    default_run_budget_usd: float = 1.0
    max_companies_per_run: int = 10
    max_drafts_per_run: int = 3
    max_results_per_source: int = 200

    # Optional LLM (disabled unless both are set). Prices are user-supplied and UNVERIFIED defaults.
    llm_enabled: bool = False
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    llm_price_in_per_mtok: float = 1.0
    llm_price_out_per_mtok: float = 5.0

    # Optional authorised keys
    himalayas_api_key: str = ""
    freelancer_oauth_token: str = ""
    upwork_api_key: str = ""

    # Reddit OAuth "script" app for Find work -> Live projects (free: https://www.reddit.com/prefs/apps)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    # Live projects: Hacker News API base (overridable for the hermetic browser test) and an optional allow-list of
    # live sources, comma separated (empty = all)
    live_hn_api_url: str = "https://hn.algolia.com/api/v1"
    live_sources: str = ""

    http_user_agent: str = "ClientHuntBot/0.1 (personal job-search tool; contact: owner)"
    run_worker_enabled: bool = True
    data_retention_days: int = 365


@lru_cache
def get_settings() -> Settings:
    return Settings()
