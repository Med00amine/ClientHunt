from datetime import datetime, timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, register

_TYPE = {"contract": "contract", "freelance": "freelance", "part_time": "part_time", "full_time": "full_time"}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


@register
class Remotive(Adapter):
    key, name = "remotive", "Remotive (public API)"
    # Remotive asks for at most ~4 fetches/day: cache for 6h.
    cache_ttl = timedelta(hours=6)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        out: list[RawOpportunity] = []
        terms = params.keywords[:5] or [""]
        for term in terms:
            q = {"category": "software-dev"}
            if term:
                q["search"] = term
            q["limit"] = str(min(params.max_results, 200))
            data = self.get_json("https://remotive.com/api/remote-jobs", q)
            for j in data.get("jobs", []):
                sal = j.get("salary") or ""
                out.append(RawOpportunity(
                    source_key=self.key, external_id=str(j.get("id", "")), url=j.get("url", ""),
                    title=j.get("title", ""), company_name=j.get("company_name", ""),
                    description=html_to_text(j.get("description", "")), tags=[j.get("category", "")] + list(j.get("tags") or []),
                    posted_at=parse_dt(j.get("publication_date")),
                    engagement_type=_TYPE.get(j.get("job_type") or "", "unknown"),
                    remote_status="remote", location_requirements=j.get("candidate_required_location", "") or "",
                    # salary is free text on Remotive; we do not guess numbers from it
                    source_type="api"))
                if sal:
                    out[-1].description += f"\n\nPublished salary text: {sal}"
        return out
