"""Real Work From Anywhere RSS (realworkfromanywhere.com). The site advertises its RSS feed, robots.txt allows it and
every listing is a work-from-anywhere role. No terms page exists to read, so polling is kept low (6 h cache) and
every listing links back to the site. Titles look like "Role at Company"."""
from datetime import timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, infer_engagement, register, to_naive_utc

URL = "https://www.realworkfromanywhere.com/rss.xml"


@register
class RealWorkFromAnywhere(Adapter):
    key, name = "rwfa", "Real Work From Anywhere (RSS)"
    cache_ttl = timedelta(hours=6)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        out: list[RawOpportunity] = []
        seen: set[str] = set()
        for item in self.get_xml(URL).iter("item"):
            link = (item.findtext("link") or "").strip()
            head = (item.findtext("title") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            if not link or not head or guid in seen:
                continue
            seen.add(guid)
            role, sep, company = head.rpartition(" at ")
            if not sep:
                role, company = head, ""
            text = html_to_text(item.findtext("description") or "")
            out.append(RawOpportunity(
                source_key=self.key, external_id=guid, url=link, title=role.strip(), company_name=company.strip(),
                description=text, posted_at=to_naive_utc(item.findtext("pubDate")), engagement_type=infer_engagement(role, text),
                remote_status="remote", location_requirements="Worldwide (work from anywhere)"))
        return out
