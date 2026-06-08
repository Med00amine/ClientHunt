from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, register

_TYPE = {"contractor": "contract", "contract": "contract", "freelance": "freelance",
         "part time": "part_time", "part-time": "part_time", "full time": "full_time", "full-time": "full_time"}


@register
class Himalayas(Adapter):
    key, name = "himalayas", "Himalayas (public API)"
    cache_ttl = timedelta(hours=12)  # data refreshes daily per docs

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        headers = {}
        if get_settings().himalayas_api_key:
            headers["Authorization"] = f"Bearer {get_settings().himalayas_api_key}"
        out, seen = [], set()
        for term in (params.keywords[:4] or ["python"]):
            for page in range(1, 4):
                q = {"q": term, "page": str(page)}
                data = self.get_json("https://himalayas.app/jobs/api/search", q, headers or None)
                jobs = data.get("jobs", [])
                if not jobs:
                    break
                for j in jobs:
                    gid = j.get("guid") or j.get("applicationLink")
                    if gid in seen:
                        continue
                    seen.add(gid)
                    pub = j.get("pubDate")
                    exp = j.get("expiryDate")
                    et = _TYPE.get(str(j.get("employmentType", "")).lower(), "unknown")
                    out.append(RawOpportunity(
                        source_key=self.key, external_id=str(gid), url=j.get("applicationLink", ""),
                        title=j.get("title", ""), company_name=j.get("companyName", ""),
                        description=html_to_text(j.get("description", "") or j.get("excerpt", "")),
                        tags=list(j.get("categories") or []),
                        posted_at=_ts(pub), deadline=_ts(exp), engagement_type=et, remote_status="remote",
                        location_requirements=_location(j),
                        budget_min=j.get("minSalary") or None, budget_max=j.get("maxSalary") or None,
                        currency=j.get("currency", "") or "",
                        rate_type={"year": "annual", "yearly": "annual", "annual": "annual", "month": "monthly",
                                   "monthly": "monthly", "hour": "hourly", "hourly": "hourly"}.get(
                            str(j.get("salaryPeriod", "")).lower(), "") if (j.get("minSalary") or j.get("maxSalary")) else ""))
        return out


def _ts(v):
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) or str(v).isdigit():
            return datetime.fromtimestamp(int(v), timezone.utc).replace(tzinfo=None)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, OSError):
        return None


def _location(j: dict) -> str:
    """locationRestrictions are strings; timezoneRestrictions are numeric UTC offsets (verified on live API)."""
    countries = [str(x) for x in (j.get("locationRestrictions") or [])]
    parts = [("Only: " + ", ".join(countries))] if countries else []
    tz = sorted(float(x) for x in (j.get("timezoneRestrictions") or []) if isinstance(x, (int, float)))
    if len(tz) >= 24:
        parts.append("Worldwide (any time zone)")
    elif tz:
        parts.append("Time zones: " + ", ".join(f"UTC{x:+g}" for x in tz))
    return "; ".join(parts)
