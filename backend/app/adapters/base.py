from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
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
    def _get_cached(self, url: str, params: dict | None, headers: dict | None, parse, validate=None) -> object:
        """GET with a DB-backed cache. `parse` turns the body text into the returned object and is also
        used to validate it, so a broken response is retried and never cached."""
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        row = self.db.get(HttpCache, key)
        if row and utcnow() - row.fetched_at < self.cache_ttl:
            try:
                cached = parse(row.body)
                if validate is None or validate(cached):
                    return cached
            except ValueError:
                pass  # an unusable cached body is simply refetched
        last_exc: Exception | None = None
        for attempt in range(3):  # read-only GET: safe to retry with backoff
            try:
                r = self.client.get(url, params=params, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise AdapterError(f"HTTP {r.status_code} from {self.key}")
                if r.status_code >= 400:
                    raise AdapterError(f"HTTP {r.status_code} from {self.key}: {r.text[:120]}")
                body = r.text
                data = parse(body)
                if validate is not None and not validate(data):
                    raise ValueError("unexpected response content")   # e.g. {"success": false}: retried, never cached
                break
            except (httpx.TransportError, AdapterError, ValueError) as e:
                last_exc = e
                if isinstance(e, AdapterError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e):
                    raise
                self.sleep(2 ** attempt)
        else:
            raise AdapterError(f"{self.key} request failed: {last_exc}")
        if row:
            row.fetched_at, row.body = utcnow(), body
        else:
            self.db.add(HttpCache(key=key, fetched_at=utcnow(), body=body))
        self.db.commit()
        return data

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None, validate=None):
        return self._get_cached(url, params, headers, json.loads, validate)

    def get_xml(self, url: str, params: dict | None = None, headers: dict | None = None):
        """RSS/Atom feed -> root element, parsed with defusedxml (feeds are untrusted input)."""
        def parse(text: str):
            try:
                return ElementTree.fromstring(_repair_xml(text).encode("utf-8"))
            except (ElementTree.ParseError, DefusedXmlException) as e:
                raise ValueError(f"invalid or unsafe XML: {e}") from e
        return self._get_cached(url, params, headers, parse)

    def sleep(self, seconds: float) -> None:  # overridable in tests
        import time
        time.sleep(seconds)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        raise NotImplementedError


registry: dict[str, Callable[..., Adapter]] = {}


def register(cls):
    registry[cls.key] = cls
    return cls


# ---------------------------------------------------------------- shared helpers for adapters
_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _repair_xml(text: str) -> str:
    """Real-world feeds often contain bare '&' (for example in URLs: ?s=200&v=4) and stray control characters. Repair
    those, nothing else; DTDs and entity declarations are still rejected by defusedxml."""
    return _BARE_AMP.sub("&amp;", _CTRL.sub("", text))

def to_naive_utc(value) -> datetime | None:
    """ISO-8601 or RFC-2822 text, or a UNIX timestamp -> naive UTC datetime (None if unparseable)."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value), timezone.utc).replace(tzinfo=None)
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(text)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except (ValueError, TypeError, OverflowError, OSError):
        return None


# Wording that decides the engagement type. Boilerplate in full-time postings contains "per hour", "short-term
# disability", "independent contractor ... as applicable" and the like, so only the TITLE, the first lines and a few
# explicit statements count; everything else is ignored.
_TITLE_CONTRACT = re.compile(r"\b(contract|contractor|freelance|freelancer|independent|temporary|temp|fixed[- ]term)\b", re.I)
_HEAD_CONTRACT = re.compile(
    r"\b(freelanc\w*|independent (contractor|consultant|developer|engineer|software)|1099|contractor|"
    r"contract (role|position|basis|engagement|work|opportunity)|on a contract|project[- ]based)\b|"
    r"[$€£]\s?\d[\d,.]*(\s?-\s?[$€£]?\d[\d,.]*)?\s?(/|per)\s?(hr|hour)\b", re.I)
_BODY_CONTRACT = re.compile(
    r"\b(this is a (fixed[- ]term |short[- ]term |6[- ]month |12[- ]month )?contract (position|role)|contract[- ]to[- ]hire|"
    r"we are looking for (a |an )?(freelance|contract)\w*|b2b contract|freelance / b2b|independent contractor "
    r"(basis|agreement|engagement))\b", re.I)
_PART = re.compile(r"\bpart[- ]time\b", re.I)
_FULL = re.compile(r"\bfull[- ]time\b", re.I)
_NO_CONTRACT_PHRASE = re.compile(r"\bno (contractors?|freelancers?|agencies|agency|c2c|third[- ]part(y|ies)|recruiters?)\b", re.I)


def infer_engagement(title: str, description: str) -> str:
    """contract | part_time | full_time | unknown, from wording only (heuristic: always read the listing)."""
    desc = _NO_CONTRACT_PHRASE.sub(" ", description or "")
    head = desc[:350]
    if _TITLE_CONTRACT.search(title or "") or _HEAD_CONTRACT.search(head) or _BODY_CONTRACT.search(desc):
        return "contract"
    if _PART.search(title or "") or _PART.search(head):
        return "part_time"
    if _FULL.search(f"{title}\n{desc}"):
        return "full_time"
    return "unknown"


JOB_BOARD_DOMAINS = ("linkedin.com", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "ycombinator.com",
                     "indeed.com", "wellfound.com", "angel.co", "bamboohr.com", "smartrecruiters.com", "notion.site",
                     "github.com", "twitter.com", "x.com", "forms.gle", "docs.google.com", "gem.com", "rippling.com",
                     "recruitee.com", "breezy.hr", "teamtailor.com", "jobvite.com", "personio", "join.com", "notion.so",
                     "weworkremotely.com", "python.org", "jobicy.com", "remotive.com", "remoteok.com", "himalayas.app")


def origin_if_company_site(url: str) -> str:
    """Origin (scheme://host) of a URL unless it points at a job board / ATS / social site; '' otherwise."""
    try:
        p = urlsplit((url or "").strip())
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    host = p.hostname.lower()
    if any(b in host for b in JOB_BOARD_DOMAINS):
        return ""
    return f"{p.scheme}://{host}"
