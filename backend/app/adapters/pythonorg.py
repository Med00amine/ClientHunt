"""Python Job Board RSS (python.org/jobs). The feed is the board's own subscription feed; robots.txt allows it.
The site's legal pages could not be read, so polling is kept low (6 h cache). Items carry no date."""
import re
from datetime import timedelta

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, infer_engagement, register

URL = "https://www.python.org/jobs/feed/rss/"
_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|work from home)\b", re.I)


@register
class PythonJobBoard(Adapter):
    key, name = "pythonorg", "Python Job Board (RSS)"
    cache_ttl = timedelta(hours=6)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        out: list[RawOpportunity] = []
        for item in self.get_xml(URL).iter("item"):
            link = (item.findtext("link") or "").strip()
            raw_title = (item.findtext("title") or "").strip()
            if not link or not raw_title:
                continue
            role, sep, company = raw_title.rpartition(", ")   # "Job title, Company"
            if not sep:
                role, company = raw_title, ""
            text = html_to_text(item.findtext("description") or "")
            location, _, body = text.partition("\n")           # the first line is the location
            location = location.strip()
            blob = f"{location}\n{body}"
            out.append(RawOpportunity(
                source_key=self.key, external_id=link.rstrip("/").rsplit("/", 1)[-1], url=link, title=role.strip(),
                company_name=company.strip(), description=body.strip() or text, tags=["python"],
                engagement_type=infer_engagement(role, body), remote_status="remote" if _REMOTE.search(blob[:600]) else "unknown",
                location_requirements=location[:200]))
        return out
