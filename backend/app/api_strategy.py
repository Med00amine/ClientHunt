from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import auth
from .db import get_db
from .services import strategy

router = APIRouter(prefix="/api", dependencies=[auth.Authed])


@router.get("/strategy")
def get_strategy(db: Session = Depends(get_db)):
    """Today's actions and what the stored data says, plus the written playbook. Read-only."""
    return strategy.build(db)
