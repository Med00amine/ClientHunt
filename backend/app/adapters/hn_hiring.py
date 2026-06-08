"""Hacker News monthly 'Ask HN: Who is hiring?' thread via the Algolia HN Search API.
Comments are free text written by third parties and are treated as untrusted data."""
import html as htmllib
import re
from datetime import datetime, timedelta, timezone

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, AdapterError, register

BASE = "https://hn.algolia.com/api/v1"
_URL = re.compile(r"https?://[^\s<>\"')]+")
_JOB_BOARDS = ("linkedin.com", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "ycombinator.com",
               "indeed.com", "wellfound.com", "angel.co", "bamboohr.com", "smartrecruiters.com", "notion.site",
               "github.com", "twitter.com", "x.com", "forms.gle", "docs.google.com", "gem.com", "rippling.com",
               "recruitee.com", "breezy.hr", "teamtailor.com", "jobvite.com", "personio", "join.com", "notion.so",
               "ycombinator.com", "linkedin.com")


@register
class HNHiring(Adapter):
    key, name = "hn_hiring", "Hacker News: Who is hiring? (Algolia API)"
    cache_ttl = timedelta(hours=12)

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        stories = self.get_json(f"{BASE}/search_by_date", {"tags": "story,author_whoishiring", "hitsPerPage": "10"})
        threads = [h for h in stories.get("hits", []) if "who is hiring" in (h.get("title") or "").lower()][:2]
        if not threads:
            raise AdapterError("could not find a current 'Who is hiring?' thread")
        out: list[RawOpportunity] = []
        seen: set[str] = set()
        for thread in threads:  # latest month + previous month (the date filter drops stale posts)
            tid = thread["objectID"]
            page, pages = 0, 1
            while page < pages and page < 4:
                data = self.get_json(f"{BASE}/search_by_date", {"tags": f"comment,story_{tid}", "hitsPerPage": "1000",
                                                                "page": str(page)})
                pages = int(data.get("nbPages") or 1)
                page += 1
                for h in data.get("hits", []):
                    if str(h.get("parent_id")) != str(tid) or h["objectID"] in seen:
                        continue  # replies, not top-level postings
                    seen.add(h["objectID"])
                    raw = self._to_raw(h)
                    if raw:
                        out.append(raw)
        return out

    def _to_raw(self, h: dict) -> RawOpportunity | None:
        text = html_to_text(h.get("comment_text") or "")
        if not text:
            return None
        first = text.split("\n", 1)[0]
        company = first.split("|")[0].strip()[:120]
        if len(company) > 80 or re.match(r"^(location|remote|company|hiring|about)\s*:", company, re.I):
            company = ""
            m = re.search(r"^\s*(?:company|employer)\s*:\s*(.+)$", text, re.I | re.M)  # key: value style posts
            if m:
                company = m.group(1).split("|")[0].strip()[:80]
        urls = [u.rstrip(".,;") for u in _URL.findall(htmllib.unescape(h.get("comment_text") or ""))]
        urls = [u for u in urls if not any(b in u.split("/")[2].lower() for b in _JOB_BOARDS)]
        urls = ["/".join(u.split("/")[:3]) for u in urls]  # origin only: the company site, not a job page
        lower = text.lower()
        et = "contract" if re.search(r"\b(contract|contractor|freelance)\b", lower) else "unknown"
        if re.search(r"\bpart[- ]time\b", lower):
            et = "part_time"
        return RawOpportunity(
            source_key=self.key, external_id=str(h["objectID"]),
            url=f"https://news.ycombinator.com/item?id={h['objectID']}",
            title=(first[:200] or "HN job posting"), company_name=company, description=text,
            company_website=urls[0] if urls else "", company_website_source="listing_text" if urls else "",
            posted_at=datetime.fromtimestamp(h["created_at_i"], timezone.utc).replace(tzinfo=None) if h.get("created_at_i") else None,
            engagement_type=et, remote_status=_remote(first.lower(), lower), location_requirements=_loc(first))


def _remote(first: str, lower: str) -> str:
    if re.search(r"\b(hybrid)\b", first):
        return "hybrid"
    if re.search(r"\b(onsite|on-site|on site)\b", first) and "remote" not in first:
        return "onsite"
    return "remote" if re.search(r"\bremote\b", lower) else "unknown"


def _loc(first: str) -> str:
    """Location is the header segment mentioning 'remote' or a place; kept verbatim (untrusted text)."""
    parts = [x.strip() for x in first.split("|")[1:]]
    seg = [x for x in parts if re.search(r"remote|worldwide|global|onsite|hybrid|\b(us|usa|uk|eu|europe|canada|emea)\b|time ?zone|\b[A-Z]{2,4}\b", x, re.I)]
    return "; ".join(seg)[:200]
