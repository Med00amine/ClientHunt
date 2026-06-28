from datetime import datetime, timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, infer_engagement, register


@register
class RemoteOK(Adapter):
    key, name = "remoteok", "Remote OK (public API)"
    cache_ttl = timedelta(hours=6)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        data = self.get_json("https://remoteok.com/api")
        out = []
        for j in data:
            if not isinstance(j, dict) or "position" not in j:  # first element is the legal notice
                continue
            lo, hi = j.get("salary_min") or None, j.get("salary_max") or None
            out.append(RawOpportunity(
                source_key=self.key, external_id=str(j.get("id") or j.get("slug", "")),
                url=j.get("url") or j.get("apply_url", ""), title=j.get("position", ""),
                company_name=j.get("company", ""), description=html_to_text(j.get("description", "")),
                tags=list(j.get("tags") or []),
                posted_at=datetime.utcfromtimestamp(int(j["epoch"])) if str(j.get("epoch", "")).isdigit() else None,
                engagement_type=infer_engagement(j.get("position", ""), html_to_text(j.get("description", ""))),
                remote_status="remote", location_requirements=j.get("location", "") or "",
                budget_min=float(lo) if lo else None, budget_max=float(hi) if hi else None,
                currency="USD" if (lo or hi) else "", rate_type="annual" if (lo or hi) else ""))
        return out[: params.max_results * 3]
