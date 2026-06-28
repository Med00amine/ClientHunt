"""Hacker News monthly 'Ask HN: Who is hiring?' thread via the Algolia HN Search API.
Comments are free text written by third parties and are treated as untrusted data."""
import html as htmllib
import re
from datetime import datetime, timedelta, timezone

from ..textutil import html_to_text
from ..types import RawOpportunity, SearchParams
from .base import Adapter, AdapterError, origin_if_company_site, register

# same template as services.leads.JOB_SEEKER_POST (kept here to avoid importing services into adapters)
JOB_SEEKER_POST = re.compile(r"(willing to relocate\s*:|r[ée]sum[ée]\s*/\s*cv\s*:|\bseeking work\b|\bavailable for (hire|freelance work)\b)", re.I)

# same pattern as services.leads.CLOSED_POST (kept here to avoid importing services into adapters)
CLOSED_POST = re.compile(r"\bclosed now\b|\bnow closed\b|\bno longer (hiring|accepting|taking)\b|"
                         r"\b(position|role|job)s? (has been |have been |is |are |was |were )?(filled|closed)\b|[\[(|]\s*closed\s*(?:[\])|:\-–—]|$)|^\s*closed\b", re.I)

BASE = "https://hn.algolia.com/api/v1"
_URL = re.compile(r"https?://[^\s<>\"')]+")


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
        if not text or JOB_SEEKER_POST.search(text):
            return None    # empty, or a person advertising themselves (not a client): never collected
        if CLOSED_POST.search(text[:300]):
            return None    # the poster edited the header to say the position is closed: not a lead
        first = text.split("\n", 1)[0]
        company = first.split("|")[0].strip()[:120]
        if len(company) > 80 or re.match(r"^(location|remote|company|hiring|about)\s*:", company, re.I):
            company = ""
            m = re.search(r"^\s*(?:company|employer)\s*:\s*(.+)$", text, re.I | re.M)  # key: value style posts
            if m:
                company = m.group(1).split("|")[0].strip()[:80]
        urls = [u.rstrip(".,;") for u in _URL.findall(htmllib.unescape(h.get("comment_text") or ""))]
        urls = [o for o in (origin_if_company_site(u) for u in urls) if o]  # origin only: the company site, not a job page
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
    if re.search(r"\b(onsite|on-site|on site|in[- ]person)\b", first) and "remote" not in first:
        return "onsite"
    return "remote" if re.search(r"\bremote\b", lower) else "unknown"


_ROLE_WORDS = re.compile(r"\b(engineer|engineers|developer|developers|manager|scientist|designer|analyst|lead|head|director|intern|"
                         r"architect|researcher|specialist|consultant|founder|cto|sre|devops|full[- ]?stack|back[- ]?end|front[- ]?end)\b", re.I)
_PLACE_HINT = re.compile(r"remote|worldwide|global|onsite|on-site|in[- ]person|hybrid|anywhere|time ?zone|"
                         r"\b(us|usa|uk|eu|emea|apac|latam|cet|est|pst|gmt|utc)\b|[A-Z][a-z]+,\s*[A-Z]{2}\b", re.I)


def _loc(first: str) -> str:
    """Location is the header segment(s) that look like a place or a work arrangement; kept verbatim (untrusted text).
    A segment that reads like a job title ("AI Engineer (£30/hr)") is never a location."""
    parts = [x.strip() for x in first.split("|")[1:]]
    seg = [x for x in parts if _PLACE_HINT.search(x) and not _ROLE_WORDS.search(x)]
    return "; ".join(seg)[:200]
