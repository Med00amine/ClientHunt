from __future__ import annotations

import json
from datetime import timedelta
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import HttpCache, utcnow
from ..types import RawOpportunity, SearchParams


class AdapterError(Exception):
    """Transient or protocol failure while querying a source."""


class AdapterUnavailable(Exception):
    """Source is not configured / not authorised. Reported honestly, never faked."""


class Adapter:
    key = ""
    name = ""
    cache_ttl = timedelta(hours=1)
    min_interval_note = ""

    def __init__(self, db: Session, client: httpx.Client | None = None):
        self.db = db
        self.client = client or httpx.Client(
            timeout=20, headers={"User-Agent": get_settings().http_user_agent}, follow_redirects=False)

    # -- cached GET (provider-aware: the cache TTL enforces documented polling limits)
    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        row = self.db.get(HttpCache, key)
        if row and utcnow() - row.fetched_at < self.cache_ttl:
            return json.loads(row.body)
        last_exc: Exception | None = None
        for attempt in range(3):  # read-only GET: safe to retry with backoff
            try:
                r = self.client.get(url, params=params, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise AdapterError(f"HTTP {r.status_code} from {self.key}")
                if r.status_code >= 400:
                    raise AdapterError(f"HTTP {r.status_code} from {self.key}: {r.text[:120]}")
                data = r.json()
                break
            except (httpx.TransportError, AdapterError, ValueError) as e:
                last_exc = e
                if isinstance(e, AdapterError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e):
                    raise
                self.sleep(2 ** attempt)
        else:
            raise AdapterError(f"{self.key} request failed: {last_exc}")
        if row:
            row.fetched_at, row.body = utcnow(), json.dumps(data)
        else:
            self.db.add(HttpCache(key=key, fetched_at=utcnow(), body=json.dumps(data)))
        self.db.commit()
        return data

    def sleep(self, seconds: float) -> None:  # overridable in tests
        import time
        time.sleep(seconds)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        raise NotImplementedError


registry: dict[str, Callable[..., Adapter]] = {}


def register(cls):
    registry[cls.key] = cls
    return cls
