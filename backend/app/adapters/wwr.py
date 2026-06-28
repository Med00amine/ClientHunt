"""We Work Remotely RSS feeds (weworkremotely.com/remote-job-rss-feed). The feeds are published by the site for
subscribers; robots.txt allows them. The site's terms page returned HTTP 403 to automated readers, so the terms
could not be read: polling is kept low (6 h cache) and every listing links back to weworkremotely.com."""
import re
from datetime import timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, AdapterError, infer_engagement, origin_if_company_site, register, to_naive_utc

BASE = "https://weworkremotely.com"
FEEDS = ("/remote-jobs.rss", "/categories/remote-full-stack-programming-jobs.rss", "/categories/remote-programming-jobs.rss",
         "/categories/remote-back-end-programming-jobs.rss", "/categories/remote-devops-sysadmin-jobs.rss")
_SITE = re.compile(r"URL:\s*</strong>\s*<a[^>]+href=\"([^\"]+)\"", re.I)


def _text(item, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


@register
class WeWorkRemotely(Adapter):
    key, name = "wwr", "We Work Remotely (RSS)"
    cache_ttl = timedelta(hours=6)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        out: list[RawOpportunity] = []
        seen: set[str] = set()
        ok = 0
        for path in FEEDS:
            root = self.get_xml(BASE + path)
            ok += 1
            for item in root.iter("item"):
                guid = _text(item, "guid") or _text(item, "link")
                link = _text(item, "link")
                if not guid or not link or guid in seen:
                    continue
                seen.add(guid)
                head = _text(item, "title")
                company, _, role = head.partition(": ")
                if not role:
                    company, role = "", head
                raw_html = _text(item, "description")
                m = _SITE.search(raw_html.replace("&amp;", "&"))
                text = html_to_text(raw_html)
                region = _text(item, "region")
                out.append(RawOpportunity(
                    source_key=self.key, external_id=guid, url=link, title=role.strip(), company_name=company.strip(),
                    company_website=origin_if_company_site(m.group(1)) if m else "",
                    company_website_source="listing_field" if m and origin_if_company_site(m.group(1)) else "",
                    description=text, tags=[t for t in (_text(item, "category"),) if t],
                    posted_at=to_naive_utc(_text(item, "pubDate")),
                    engagement_type=infer_engagement(role, text), remote_status="remote", location_requirements=region))
        if not ok:
            raise AdapterError("no We Work Remotely feed could be read")
        return out
