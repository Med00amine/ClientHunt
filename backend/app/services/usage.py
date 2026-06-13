from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import UsageEvent, utcnow


def record(db: Session, kind: str, provider: str, units: float, cost: float, run_id: int | None = None,
           estimated: bool = True, note: str = "") -> UsageEvent:
    ev = UsageEvent(run_id=run_id, kind=kind, provider=provider, units=units, cost_usd=cost,
                    estimated=estimated, note=note)
    db.add(ev)
    db.commit()
    return ev


def month_spend(db: Session, now: datetime | None = None) -> float:
    now = now or utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float(db.scalar(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0))
                           .where(UsageEvent.at >= start)) or 0.0)


def run_spend(db: Session, run_id: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0))
                           .where(UsageEvent.run_id == run_id)) or 0.0)


def budget_remaining(db: Session, run_id: int, run_cap: float) -> tuple[float, str]:
    """Remaining paid-spend allowance for this run and the reason that limits it."""
    s = get_settings()
    month_left = s.monthly_budget_usd - month_spend(db)
    run_left = run_cap - run_spend(db, run_id)
    if month_left <= run_left:
        return max(0.0, month_left), "monthly budget"
    return max(0.0, run_left), "per-run budget"


def llm_cost(tokens_in: int, tokens_out: int) -> float:
    s = get_settings()
    return tokens_in / 1e6 * s.llm_price_in_per_mtok + tokens_out / 1e6 * s.llm_price_out_per_mtok
