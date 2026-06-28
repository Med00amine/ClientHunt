"""Jobicy remote-jobs API (https://jobicy.com/jobs-rss-feed). No key. Terms (read 2026): credit Jobicy, application
links must lead to the Jobicy listing, data may be stored and cached, poll at most about once per hour, results cover
the last 7 days. The listing URL stored here is Jobicy's own page, so attribution and link-back are automatic."""
import html
from datetime import timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, AdapterError, infer_engagement, register, to_naive_utc

API = "https://jobicy.com/api/jobs"
_TYPE = {"contract": "contract", "freelance": "freelance", "part-time": "part_time", "part time": "part_time",
         "full-time": "full_time", "full time": "full_time", "internship": "internship"}
_PERIOD = {"yearly": "annual", "year": "annual", "annual": "annual", "monthly": "monthly", "month": "monthly",
           "hourly": "hourly", "hour": "hourly"}
_PRIORITY = ("contract", "freelance", "part_time", "full_time", "internship")


def _as_list(v) -> list[str]:
    if v in (None, ""):
        return []
    return [html.unescape(str(x)) for x in v] if isinstance(v, (list, tuple)) else [html.unescape(str(v))]


def _num(v) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


@register
class Jobicy(Adapter):
    key, name = "jobicy", "Jobicy (public API)"
    cache_ttl = timedelta(hours=1)  # documented: automated passes no more than once per hour

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        out: list[RawOpportunity] = []
        seen: set[str] = set()
        # Jobicy only accepts tags of 3-50 characters (a 2-letter tag such as "ai" is rejected with HTTP 400)
        terms = [t.strip() for t in (params.keywords or ["python"]) if 3 <= len(t.strip()) <= 50][:6] or ["python"]
        answered = 0
        for term in terms:
            try:
                data = self.get_json(API, {"count": "100", "tag": term}, validate=lambda d: isinstance(d, dict) and d.get("success") is not False)
            except AdapterError as e:
                if "HTTP 400" in str(e):
                    continue  # this one keyword is not acceptable to the API; the others still count
                raise
            answered += 1
            for j in data.get("jobs", []):
                jid = str(j.get("id", ""))
                if not jid or jid in seen or not j.get("url"):
                    continue
                seen.add(jid)
                types = [_TYPE.get(t.strip().lower(), "") for t in _as_list(j.get("jobType"))]
                et = next((t for t in _PRIORITY if t in types), "unknown")
                text = html_to_text(j.get("jobDescription") or j.get("jobExcerpt") or "")
                if et == "unknown":
                    et = infer_engagement(html.unescape(j.get("jobTitle", "")), text)
                lo, hi = _num(j.get("salaryMin")), _num(j.get("salaryMax"))
                out.append(RawOpportunity(
                    source_key=self.key, external_id=jid, url=j["url"], title=html.unescape(j.get("jobTitle", "")),
                    company_name=html.unescape(j.get("companyName", "")), description=text,
                    tags=_as_list(j.get("jobIndustry")) + _as_list(j.get("jobLevel")),
                    posted_at=to_naive_utc(j.get("pubDate")), engagement_type=et, remote_status="remote",
                    location_requirements=", ".join(x.strip() for x in _as_list(j.get("jobGeo")) if x.strip()),
                    budget_min=lo, budget_max=hi, currency=(j.get("salaryCurrency") or "") if (lo or hi) else "",
                    rate_type=_PERIOD.get(str(j.get("salaryPeriod", "")).lower(), "") if (lo or hi) else ""))
        if not answered:
            raise AdapterError("jobicy rejected every search keyword")
        return out
