"""Live view of clients asking for help right now, with the emails they published.

Sources (all read through public APIs or feeds the sites publish and their robots.txt allows; nothing gets past a
login, a block or a rate limit):
  hn_freelance  Hacker News monthly "Freelancer? Seeking freelancer?" threads: only "SEEKING FREELANCER" posts.
  hn_hiring     Hacker News monthly "Who is hiring?" threads (two months): only contract, freelance or part-time posts.
  marketplaces  Client project marketplaces' own RSS feeds: Codeur.com (French) and Mostaql (Arabic). Every item is a
                client describing a project; you answer on the platform, so no emails are taken from them.
  bluesky       Bluesky's public post search (api.bsky.app), run with client-intent phrases ("looking for a freelance",
                "client needs", "#hiring python" ...) and kept only when the post asks for project work.
  mastodon      Public hashtag timelines (#hiring, #FediHire, #GetFediHired, #freelance, #techjobs ...) on several servers.
  bounties      Open, unassigned GitHub issues carrying Algora's funded "💎 Bounty" label (paid on merge). Plain "bounty"
                labels are ignored: they are full of fake "escrow" offers.
  boards        Contract, freelance and part-time jobs from Remotive, Jobicy, Himalayas, RemoteOK and Working Nomads,
                polled within the limits their docs state. Remotive asks that emails are not collected.
  reddit        [Hiring] posts, only through Reddit's OAuth API and only when a free "script" app is configured
                (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET). Reddit's robots.txt disallows all other automated access,
                so without keys Reddit is simply left out (no error).
People advertising themselves ("SEEKING WORK", "[For Hire]", #OpenToWork) are skipped: they are not clients and their
addresses are never collected. Sources are asked in parallel; one that is busy or down is reported in `sources` and the
others still answer. Results stay in a short in-memory cache and are not written to the database."""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from ..adapters.base import infer_engagement, to_naive_utc
from ..config import get_settings
from ..scoring import score
from ..textutil import html_to_text
from ..types import RawOpportunity
from .emailtable import contact_rows

CACHE_SECONDS = 15 * 60
BUSY_SECONDS = 3 * 60               # after a "slow down" answer, wait before asking that source again
DEFAULT_MAX_DAYS = 45
MAX_PER_POSTER = 6                  # job-repost accounts post dozens of ads; keep their best few
DEFAULT_QUERIES = [
    "machine learning", "LLM", "RAG", "AI agent", "NLP", "computer vision", "python", "data science", "FastAPI", "AWS",
    "chatbot", "OpenAI", "GPT", "AI", "automation", "scraping", "data engineer", "Django", "API", "backend", "bot",
    # French (Codeur.com) and Arabic (Mostaql) clients describe the same work in their own words
    "IA", "intelligence artificielle", "automatisation", "données", "développeur Python",
    "ذكاء اصطناعي", "الذكاء الاصطناعي", "بايثون", "تعلم الآلة", "بوت", "أتمتة", "تحليل البيانات", "برمجة"]
MAX_QUERIES = 50
SOURCES = ("hn_freelance", "hn_hiring", "marketplaces", "bluesky", "mastodon", "bounties", "boards", "reddit")
SOURCE_NAMES = {"hn_freelance": "HN: Seeking freelancer", "hn_hiring": "HN: Who is hiring", "marketplaces": "Client marketplaces",
                "bluesky": "Bluesky", "mastodon": "Mastodon", "bounties": "GitHub bounties", "boards": "Remote boards",
                "reddit": "Reddit"}
SUBREDDITS = ["forhire", "hiring", "jobbit", "freelance_forhire", "PythonJobs", "MachineLearningJobs", "remotepython",
              "RemoteJobs", "WorkOnline"]
MASTODON_TAGS = [("mastodon.social", "hiring"), ("mastodon.social", "FediHire"), ("mastodon.social", "GetFediHired"),
                 ("mastodon.social", "freelance"), ("mastodon.social", "remotejobs"), ("mastodon.social", "techjobs"),
                 ("mastodon.social", "AIjobs"), ("mastodon.social", "jobs"), ("hachyderm.io", "hiring"),
                 ("hachyderm.io", "FediHire"), ("fosstodon.org", "FediHire"), ("mastodon.online", "hiring"),
                 ("techhub.social", "hiring")]
BLUESKY_QUERIES = ['"looking for a freelance"', '"looking for a developer"', '"looking for an AI"', '"client needs"',
                   '"need a developer"', '"looking for someone to build"', '"paid project"', "#hiring python",
                   "#hiring LLM", "#hiring machine learning", "#freelance AI", "contract AI engineer", "hiring freelance AI"]
# a client describing work they will pay for (not a job ad): ranked a little higher
DIRECT_SOURCES = ("hn_freelance", "marketplaces", "bounties")
MARKET_FEEDS = [("Codeur.com · FR", "https://www.codeur.com/projects.rss"),
                ("Codeur.com · FR", "https://www.codeur.com/projects/c/developpement.rss"),
                ("Codeur.com · FR", "https://www.codeur.com/projects/c/developpement/sc/python.rss"),
                ("Mostaql · AR", "https://mostaql.com/rss"),
                ("Mostaql · AR", "https://mostaql.com/rss?category=development")]

_SEEKING_FREELANCER = re.compile(r"^\W*seeking\s+(a\s+)?freelancers?\b", re.I)
_REDDIT_HIRING = re.compile(r"[\[(]\s*hiring\s*[\])]", re.I)
_REDDIT_FOR_HIRE = re.compile(r"[\[(]\s*for\s*hire\s*[\])]|\bfor hire\b", re.I)
_CLOSED = re.compile(r"\b(closed|filled|no longer (hiring|accepting|available))\b", re.I)
_SELF_PROMO = re.compile(r"#?open\s?to\s?work|\bhire me\b|\bi'?m (now )?(available|open to|looking for (work|a job|my next|new))|"
                         r"\b(i am|i'm) (a|an) [\w\s-]{0,40}(looking|available)|\blooking for (work|a (new )?(job|role|position|gig))\b|"
                         r"\bavailable for (hire|freelance|work|projects)\b|#?forhire\b|\bmy services\b|\bseeking work\b", re.I)
_CLIENT_ASK = re.compile(r"\b(hiring|we'?re looking for|looking for (a|an|someone)|seeking (a|an)|we need|need (a|an|someone|help)|"
                         r"job|contract|freelance (role|gig|project|position)|position|role|opening|apply)\b", re.I)
# stricter wording for free-text search (Bluesky): someone asking for help, not news or chat about hiring
_INTENT = re.compile(r"\b(we'?re (looking|hiring|seeking)|we are (looking|hiring|seeking)|i'?m (looking|hiring|seeking) for (a|an|someone)|"
                     r"i am (looking|hiring|seeking) for (a|an|someone)|looking for (a|an|someone|freelancers?|contractors?|developers?)|"
                     r"(is|are|now) hiring|hiring alert|client needs|needs? (a|an|someone)|seeking (a|an|freelancers?|contractors?)|"
                     r"open role|position open|job opening|who can (build|help|make|create))\b", re.I)
_PROJECT = re.compile(r"\b(contract|contractor|freelanc\w*|part[- ]time|project|gig|consultant|consulting|hourly|per hour|"
                      r"short[- ]term|bounty|paid task)\b|\d\s?(usd|\$|€|£)?\s?/\s?(hr|hour)\b", re.I)
_AMOUNT = re.compile(r"^\$\s?\d[\d,.]*k?$", re.I)

_cache: dict[tuple, tuple[float, object]] = {}
_busy: dict[str, float] = {}
_lock = threading.Lock()
_token: dict = {}


class LiveSourceError(Exception):
    pass


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _busy.clear()
        _token.clear()


def reddit_configured() -> bool:
    s = get_settings()
    return bool(s.reddit_client_id and s.reddit_client_secret)


def _cached(key: tuple, now: float, load, ttl: float = CACHE_SECONDS):
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = load()
    with _lock:
        _cache[key] = (now, value)
    return value


def _get(client: httpx.Client, url: str, label: str, now: float, **kw) -> httpx.Response:
    with _lock:
        if _busy.get(label, 0) > now:
            raise LiveSourceError(f"{label} is busy right now; it will be asked again in a few minutes.")
    try:
        r = client.get(url, **kw)
    except httpx.TransportError as e:
        raise LiveSourceError(f"could not reach {label} ({type(e).__name__})") from e
    if r.status_code == 429 or (r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0"):
        with _lock:
            _busy[label] = now + BUSY_SECONDS
        raise LiveSourceError(f"{label} is busy right now; it will be asked again in a few minutes.")
    if r.status_code >= 400:
        raise LiveSourceError(f"{label} answered HTTP {r.status_code}")
    return r


def _get_json(client: httpx.Client, url: str, label: str, now: float, **kw):
    try:
        return _get(client, url, label, now, **kw).json()
    except ValueError as e:
        raise LiveSourceError(f"{label} returned an unreadable response") from e


def _parallel(fn, items: list, workers: int = 6) -> list[tuple[object, object]]:
    """[(item, result or LiveSourceError)] for fn(item) run on a few threads."""
    def safe(item):
        try:
            return item, fn(item)
        except LiveSourceError as e:
            return item, e
    if len(items) <= 1:
        return [safe(i) for i in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        return list(pool.map(safe, items))


def _ts(v) -> int | None:
    dt = to_naive_utc(v)
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt else None


def _post(source: str, pid: str, url: str, title: str, text: str, ts, company: str = "", poster: str = "",
          engagement: str = "", where: str = "", emails_allowed: bool = True, budget: str = "") -> dict:
    return {"id": f"{source}:{pid}", "source": source, "url": url, "title": title[:200], "company": company[:80],
            "text": text, "poster": poster, "posted_ts": ts, "engagement": engagement or infer_engagement(title, text),
            "where": where, "emails_allowed": emails_allowed, "budget": budget[:60]}


# ---------------------------------------------------------------- Hacker News
def _hn_threads(client: httpx.Client, title: str, now: float, n: int, author: str = "") -> list[dict]:
    def load():
        data = _get_json(client, f"{get_settings().live_hn_api_url}/search_by_date", "Hacker News", now, params={
            "query": f'"{title}"', "tags": f"story,author_{author}" if author else "story", "hitsPerPage": "20"})
        hits = [h for h in data.get("hits", []) if title.lower() in (h.get("title") or "").lower()
                and (h.get("title") or "").lower().startswith("ask hn")]
        hits.sort(key=lambda h: -(h.get("created_at_i") or 0))
        return [h for h in hits if (h.get("num_comments") or 0) >= 10][:n]   # skip near-empty duplicate threads
    return _cached(("hn_threads", title, n, author), now, load)


def _hn_comments(client: httpx.Client, story_id: str, now: float) -> list[dict]:
    def load():
        out, page, pages = [], 0, 1
        while page < pages and page < 3:
            data = _get_json(client, f"{get_settings().live_hn_api_url}/search_by_date", "Hacker News", now,
                             params={"tags": f"comment,story_{story_id}", "hitsPerPage": "1000", "page": str(page)})
            pages = int(data.get("nbPages") or 1)
            page += 1
            out += [h for h in data.get("hits", []) if str(h.get("parent_id")) == str(story_id)]  # top level only
        return out
    return _cached(("hn_comments", story_id), now, load)


def _hn_posts(client: httpx.Client, which: str, now: float) -> list[dict]:
    title, n, author = ("Seeking freelancer", 6, "") if which == "hn_freelance" else ("Who is hiring", 2, "whoishiring")
    posts = []
    for thread in _hn_threads(client, title, now, n, author):
        for h in _hn_comments(client, thread["objectID"], now):
            text = html_to_text(h.get("comment_text") or "", 6000)   # html_to_text decodes &lt; itself: unescaping first would eat "<a@b.c>"
            if not text:
                continue
            first = text.split("\n", 1)[0]
            if which == "hn_freelance":
                if not _SEEKING_FREELANCER.search(text):
                    continue          # "SEEKING WORK" = a freelancer advertising: not a client
                body = _SEEKING_FREELANCER.sub("", text, count=1).lstrip(" -–—:|\n")
                head = body.split("\n", 1)[0]
                company = head.split("|")[0].strip() if "|" in head else ""
                engagement = "freelance"
            else:
                if re.search(r"willing to relocate\s*:|seeking work", text, re.I) or _CLOSED.search(first):
                    continue
                engagement = infer_engagement(first, text)
                if engagement not in ("contract", "part_time"):
                    continue          # full-time jobs belong to Listings, not here
                company, head = first.split("|")[0].strip(), first
            company = re.sub(r"\(?\s*(https?://|www\.)\S*\s*\)?", "", company).strip(" -–—:|")   # "Acme (https://acme.io)"
            posts.append(_post(which, h["objectID"], f"https://news.ycombinator.com/item?id={h['objectID']}",
                               head or first, text, h.get("created_at_i"), company if len(company) <= 80 else "",
                               engagement=engagement))
    return posts


# ---------------------------------------------------------------- client project marketplaces (RSS)
def _rss_items(client: httpx.Client, url: str, label: str, now: float) -> list[dict]:
    def load():
        r = _get(client, url, label, now)
        try:
            root = ElementTree.fromstring(r.content)
        except (ElementTree.ParseError, DefusedXmlException) as e:
            raise LiveSourceError(f"{label} returned an unreadable feed") from e
        return [{"title": it.findtext("title") or "", "link": it.findtext("link") or "", "guid": it.findtext("guid") or "",
                 "description": it.findtext("description") or "", "date": it.findtext("pubDate") or ""}
                for it in root.iter("item")]
    return _cached(("rss", url), now, load)


def _market_posts(client: httpx.Client, now: float) -> tuple[list[dict], list[str]]:
    out, errors = [], []
    for (label, url), res in _parallel(lambda f: _rss_items(client, f[1], f[0].split(" ·")[0], now), MARKET_FEEDS):
        if isinstance(res, LiveSourceError):
            errors.append(str(res))
            continue
        for it in res:
            body = html_to_text(it["description"], 4000)
            budget = ""
            m = re.search(r"Budget\s*:\s*(.+?)\s*-\s*Cat", body)          # Codeur: "Budget : 500 € à 1 000 € - Catégories : ..."
            if m:
                budget = m.group(1)
            body = re.sub(r"\s*Voir ce projet sur Codeur\s*$", "", body)
            title = html_to_text(it["title"], 300)                       # Codeur double-escapes: "d&#39;achat"
            pid = (it["guid"] or it["link"]).strip()
            out.append(_post("marketplaces", f"{label.split(' ·')[0]}:{pid}", it["link"].strip(), title, f"{title}\n{body}",
                             _ts(it["date"]), engagement="freelance", where=label, emails_allowed=False, budget=budget))
    if errors and not out:
        raise LiveSourceError("; ".join(errors[:2]))
    return out, errors


# ---------------------------------------------------------------- Bluesky (public search)
def _bluesky_posts(client: httpx.Client, now: float) -> tuple[list[dict], list[str]]:
    def search(q: str):
        return _cached(("bluesky", q), now, lambda: _get_json(
            client, "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", "Bluesky", now,
            params={"q": q, "limit": "50", "sort": "latest"}))
    out, errors, seen = [], [], set()
    for _q, res in _parallel(search, BLUESKY_QUERIES):
        if isinstance(res, LiveSourceError):
            errors.append(str(res))
            continue
        for p in (res or {}).get("posts", []):
            uri = p.get("uri") or ""
            if not uri or uri in seen:
                continue
            seen.add(uri)
            rec = p.get("record") or {}
            ext = ((p.get("embed") or {}).get("external") or {})
            links = [f.get("uri", "") for fa in rec.get("facets") or [] for f in fa.get("features") or [] if f.get("uri")]
            text = "\n".join(x for x in [rec.get("text") or "", ext.get("title") or "", ext.get("description") or "",
                                         " ".join(links)] if x)
            if not text or _SELF_PROMO.search(text) or not _INTENT.search(text) or not _PROJECT.search(text):
                continue          # people advertising themselves, chat or news about hiring, or not project work
            if infer_engagement(text.split("\n", 1)[0], text) == "full_time":
                continue
            handle = (p.get("author") or {}).get("handle") or ""
            out.append(_post("bluesky", uri, f"https://bsky.app/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}",
                             (rec.get("text") or "").split("\n", 1)[0], text, _ts(rec.get("createdAt") or p.get("indexedAt")),
                             poster=f"@{handle}" if handle else ""))
    if errors and not out:
        raise LiveSourceError(errors[0])
    return out, errors


# ---------------------------------------------------------------- Mastodon
def _mastodon_posts(client: httpx.Client, now: float) -> tuple[list[dict], list[str]]:
    def timeline(ht: tuple[str, str]):
        host, tag = ht
        return _cached(("mastodon", host, tag), now, lambda: _get_json(
            client, f"https://{host}/api/v1/timelines/tag/{tag}", f"Mastodon ({host})", now, params={"limit": "40"}))
    out, errors, seen = [], [], set()
    for (host, tag), data in _parallel(timeline, MASTODON_TAGS):
        if isinstance(data, LiveSourceError):
            errors.append(str(data))
            continue
        for s in data if isinstance(data, list) else []:
            uri = s.get("uri") or s.get("url") or ""
            if not uri or uri in seen or s.get("sensitive") or s.get("reblog"):
                continue
            seen.add(uri)
            text = html_to_text(s.get("content") or "", 4000)
            if not text or _SELF_PROMO.search(text) or not _CLIENT_ASK.search(text) or not _PROJECT.search(text):
                continue          # people advertising themselves, a post that asks for nobody, or not project work
            if infer_engagement(text.split("\n", 1)[0], text) == "full_time":
                continue          # permanent jobs belong to Listings, not here
            acct = (s.get("account") or {}).get("acct") or ""
            out.append(_post("mastodon", uri, s.get("url") or uri, text.split("\n", 1)[0], text, _ts(s.get("created_at")),
                             poster=f"@{acct}" + ("" if "@" in acct else f"@{host}"), where=f"#{tag}"))
    if errors and not out:
        raise LiveSourceError("; ".join(errors[:2]))
    return out, errors


# ---------------------------------------------------------------- GitHub: Algora-funded bounties
def _bounty_posts(client: httpx.Client, now: float) -> list[dict]:
    since = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=60)).date().isoformat()
    data = _cached(("github_bounties", since), now, lambda: _get_json(
        client, "https://api.github.com/search/issues", "GitHub", now, headers={"Accept": "application/vnd.github+json"},
        params={"q": f'label:"💎 Bounty" state:open created:>{since}', "sort": "created", "order": "desc", "per_page": "100"}),
        ttl=3600)
    out = []
    for i in data.get("items", []):
        if i.get("assignee") or i.get("pull_request"):
            continue          # someone is already on it, or it is a pull request
        labels = [lb.get("name", "") for lb in i.get("labels") or []]
        amount = next((x for x in labels if _AMOUNT.match(x.strip())), "")
        if not amount:
            m = re.search(r"\[\s*(\$\s?\d[\d,.]*k?)\s*\]", i.get("title") or "", re.I)   # "[$400] Per-service images"
            amount = m.group(1) if m else ""
        repo = (i.get("repository_url") or "").split("/repos/")[-1]
        out.append(_post("bounties", str(i.get("id")), i.get("html_url", ""), f"{i.get('title', '')} ({repo})",
                         f"{i.get('title', '')}\n{repo}\n{(i.get('body') or '')[:4000]}", _ts(i.get("created_at")),
                         company=repo.split("/")[0], poster=(i.get("user") or {}).get("login", ""), engagement="freelance",
                         where="Algora on GitHub", emails_allowed=False, budget=amount))
    return out


# ---------------------------------------------------------------- remote boards (contract / freelance / part-time only)
def _board_posts(client: httpx.Client, now: float) -> tuple[list[dict], list[str]]:
    def remotive():      # max ~4 fetches a day, link back, do not collect emails
        data = _cached(("remotive",), now, lambda: _get_json(client, "https://remotive.com/api/remote-jobs", "Remotive", now), ttl=6 * 3600)
        return [_post("boards", f"remotive:{j.get('id')}", j.get("url", ""), j.get("title", ""),
                      f"{j.get('title', '')}\n{html_to_text(j.get('description') or '', 4000)}", _ts(j.get("publication_date")),
                      j.get("company_name", ""), engagement="part_time" if j["job_type"] == "part_time" else "contract",
                      where="Remotive", emails_allowed=False)
                for j in data.get("jobs", []) if j.get("job_type") in ("contract", "freelance", "part_time")]

    def jobicy():        # automated passes at most hourly
        data = _cached(("jobicy",), now, lambda: _get_json(client, "https://jobicy.com/api/v2/remote-jobs", "Jobicy", now,
                                                           params={"count": "100"}), ttl=3600)
        out = []
        for j in data.get("jobs", []):
            jt = j.get("jobType")
            types = [str(t).lower() for t in (jt if isinstance(jt, list) else [jt or ""])]
            if any(t in ("contract", "freelance", "part-time") for t in types):
                out.append(_post("boards", f"jobicy:{j.get('id')}", j.get("url", ""), j.get("jobTitle", ""),
                                 f"{j.get('jobTitle', '')}\n{html_to_text(j.get('jobDescription') or j.get('jobExcerpt') or '', 4000)}",
                                 _ts(j.get("pubDate")), j.get("companyName", ""),
                                 engagement="part_time" if "part-time" in types else "contract", where="Jobicy"))
        return out

    def himalayas():     # data refreshes daily
        out = []
        for term in ("machine learning", "LLM", "python"):
            data = _cached(("himalayas", term), now, lambda: _get_json(
                client, "https://himalayas.app/jobs/api/search", "Himalayas", now, params={"q": term, "page": "1"}), ttl=12 * 3600)
            for j in data.get("jobs", []):
                et = str(j.get("employmentType") or "").lower()
                if et in ("contractor", "part time", "temporary"):
                    out.append(_post("boards", f"himalayas:{j.get('guid') or j.get('applicationLink')}", j.get("applicationLink", ""),
                                     j.get("title", ""), f"{j.get('title', '')}\n{html_to_text(j.get('description') or j.get('excerpt') or '', 4000)}",
                                     _ts(j.get("pubDate")), j.get("companyName", ""),
                                     engagement="part_time" if et == "part time" else "contract", where="Himalayas"))
        return out

    def remoteok():      # link back and name Remote OK as the source (done: the row links to the listing)
        data = _cached(("remoteok",), now, lambda: _get_json(client, "https://remoteok.com/api", "RemoteOK", now), ttl=6 * 3600)
        out = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or not j.get("id"):
                continue          # the first element is the API's legal notice
            desc = html_to_text(j.get("description") or "", 4000)
            tags = [str(t).lower() for t in j.get("tags") or []]
            eng = infer_engagement(j.get("position", ""), desc)
            if eng in ("contract", "part_time") or any(t in ("contract", "contractor", "freelance", "part time", "part-time") for t in tags):
                out.append(_post("boards", f"remoteok:{j['id']}", j.get("url", ""), j.get("position", ""),
                                 f"{j.get('position', '')}\n{desc}\n{' '.join(tags)}", _ts(j.get("date")), j.get("company", ""),
                                 engagement=eng if eng in ("contract", "part_time") else "contract", where="RemoteOK"))
        return out

    def workingnomads():
        data = _cached(("workingnomads",), now, lambda: _get_json(
            client, "https://www.workingnomads.com/api/exposed_jobs/", "Working Nomads", now), ttl=6 * 3600)
        out = []
        for j in data if isinstance(data, list) else []:
            desc = html_to_text(j.get("description") or "", 4000)
            eng = infer_engagement(j.get("title", ""), desc)
            if eng in ("contract", "part_time"):
                out.append(_post("boards", f"workingnomads:{j.get('url')}", j.get("url", ""), j.get("title", ""),
                                 f"{j.get('title', '')}\n{desc}", _ts(j.get("pub_date")), j.get("company_name", ""),
                                 engagement=eng, where="Working Nomads"))
        return out

    out, errors = [], []
    for _fn, res in _parallel(lambda f: f(), [remotive, jobicy, himalayas, remoteok, workingnomads]):
        if isinstance(res, LiveSourceError):
            errors.append(str(res))
        else:
            out += res
    if errors and not out:
        raise LiveSourceError("; ".join(errors))
    return out, errors


# ---------------------------------------------------------------- Reddit (OAuth only)
def _reddit_item(pid: str, title: str, body: str, flair: str, author: str, url: str, ts, sub: str) -> dict | None:
    hiring = _REDDIT_HIRING.search(title) or ("hiring" in flair.lower() and "for hire" not in flair.lower())
    if not hiring or _REDDIT_FOR_HIRE.search(title) or body in ("[removed]", "[deleted]") or _CLOSED.search(flair):
        return None
    text = f"{title}\n{body}"
    eng = infer_engagement(title, text)
    return _post("reddit", pid, url, _REDDIT_HIRING.sub("", title).strip(" -–—:|"), text, ts,
                 poster=f"u/{author}" if author and author != "[deleted]" else "",
                 engagement=eng if eng != "unknown" else "freelance", where=f"r/{sub}" if sub else "")


def _reddit_token(client: httpx.Client, now: float) -> str:
    with _lock:
        if _token.get("value") and _token.get("expires", 0) > now + 60:
            return _token["value"]
    s = get_settings()
    try:
        r = client.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                        auth=(s.reddit_client_id, s.reddit_client_secret), headers={"User-Agent": s.http_user_agent})
    except httpx.TransportError as e:
        raise LiveSourceError(f"could not reach Reddit ({type(e).__name__})") from e
    if r.status_code in (400, 401, 403):
        raise LiveSourceError("Reddit refused the app credentials. Check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env.")
    if r.status_code >= 400:
        raise LiveSourceError(f"Reddit answered HTTP {r.status_code} for the access token")
    data = r.json()
    with _lock:
        _token.update(value=data["access_token"], expires=now + int(data.get("expires_in") or 3600))
    return data["access_token"]


def _reddit_posts(client: httpx.Client, now: float, subs: list[str]) -> list[dict]:
    headers = {"Authorization": f"Bearer {_reddit_token(client, now)}", "User-Agent": get_settings().http_user_agent}
    data = _cached(("reddit", tuple(subs)), now, lambda: _get_json(
        client, f"https://oauth.reddit.com/r/{'+'.join(subs)}/new", "Reddit", now,
        params={"limit": "100", "raw_json": "1"}, headers=headers))
    out = []
    for c in (data.get("data") or {}).get("children", []):
        p = c.get("data") or {}
        if p.get("removed_by_category") or p.get("over_18"):
            continue
        item = _reddit_item(p.get("id", ""), p.get("title") or "", p.get("selftext") or "", p.get("link_flair_text") or "",
                            p.get("author") or "", "https://www.reddit.com" + (p.get("permalink") or ""),
                            int(p.get("created_utc") or 0) or None, p.get("subreddit") or "")
        if item:
            out.append(item)
    return out


# ---------------------------------------------------------------- shaping and search
def _matches(text: str, queries: list[str]) -> list[str]:
    low = text.lower()
    return [q for q in queries if re.search(r"(?<![a-z0-9])" + re.escape(q.lower()) + r"(?![a-z0-9])", low)]


def _source_name(p: dict) -> str:
    if p["source"] in ("boards", "marketplaces", "bounties"):
        return p["where"] or SOURCE_NAMES[p["source"]]
    return SOURCE_NAMES[p["source"]] + (f" {p['where']}" if p.get("where") else "")


def _shape(p: dict, queries: list[str], now_dt: datetime) -> dict | None:
    hits = _matches(p["text"], queries)
    if not hits:
        return None
    posted = datetime.fromtimestamp(int(p["posted_ts"]), timezone.utc).replace(tzinfo=None) if p.get("posted_ts") else None
    remote = "remote" if re.search(r"\bremote\b|\banywhere\b|\bworldwide\b", p["text"], re.I) else "unknown"
    fit = score(RawOpportunity(source_key=p["source"], url=p["url"], title=p["title"], description=p["text"],
                               posted_at=posted, engagement_type=p["engagement"], remote_status=remote), None)
    emails = contact_rows(p["text"], company=p["company"], poster=p.get("poster", "")) if p.get("emails_allowed", True) else []
    age_min = int((now_dt - posted).total_seconds() // 60) if posted else None
    fresh = 8 if age_min is not None and age_min < 3 * 1440 else 4 if age_min is not None and age_min < 14 * 1440 else 0
    direct = p["source"] in DIRECT_SOURCES
    return {
        "id": p["id"], "source": p["source"], "source_name": _source_name(p),
        "title": p["title"] or p["text"][:120], "url": p["url"],
        "company": p["company"] or next((e["company"] for e in emails if e["company"]), ""),
        "poster": p.get("poster", ""), "engagement": p["engagement"], "remote": remote, "budget": p.get("budget", ""),
        "posted_at": posted.isoformat() + "Z" if posted else None, "age_minutes": age_min,
        "excerpt": re.sub(r"\s+", " ", p["text"])[:400], "matched": hits, "emails": emails,
        "fit": fit["total"], "matched_skills": fit["matched_skills"], "direct": direct,
        # transparent heuristic (0-100): skill fit, plus a published email, plus a direct client project, plus freshness
        "worth": round(max(0.0, min(100.0, fit["total"] + (12 if emails else 0) + (10 if direct else 0) + fresh)), 1),
    }


_REPOST_PREFIX = re.compile(r"^\W*(open role|now hiring|we'?re hiring|position open|hiring alert|new job opening|job opening|"
                            r"new remote job alert|remote[- ]first|fully remote|global remote role|work from anywhere)\W*", re.I)


def _dedupe_key(r: dict) -> str:
    """Job-repost accounts post the same ad on several networks with a different emoji header: one row per ad."""
    t = _REPOST_PREFIX.sub("", r["title"])
    return re.sub(r"[^\w]+", " ", t.lower()).strip()[:90] or r["id"]


def _fetch_source(s: str, client: httpx.Client, now: float, subs: list[str]) -> tuple[list[dict], list[str]]:
    if s == "reddit":
        return _reddit_posts(client, now, subs), []
    if s == "marketplaces":
        return _market_posts(client, now)
    if s == "bluesky":
        return _bluesky_posts(client, now)
    if s == "mastodon":
        return _mastodon_posts(client, now)
    if s == "bounties":
        return _bounty_posts(client, now), []
    if s == "boards":
        return _board_posts(client, now)
    return _hn_posts(client, s, now), []


def search_projects(queries: list[str] | None = None, sources: list[str] | None = None, sort: str = "best",
                    only_email: bool = False, limit: int = 60, subreddits: list[str] | None = None,
                    client: httpx.Client | None = None, now: float | None = None,
                    max_days: int = DEFAULT_MAX_DAYS) -> dict:
    """Client posts from every chosen source that mention any query, merged and ranked. Nothing is stored.
    A source that fails is reported in `sources` (and `errors`); the others still return results."""
    qs = [q.strip() for q in (queries or DEFAULT_QUERIES) if q and q.strip()][:MAX_QUERIES] or DEFAULT_QUERIES
    srcs = [s for s in (sources or SOURCES) if s in SOURCES] or list(SOURCES)
    if not reddit_configured():   # Reddit's robots.txt disallows all automated access: only its OAuth API is used
        srcs = [s for s in srcs if s != "reddit"]
    allowed = {x.strip() for x in get_settings().live_sources.split(",") if x.strip()}
    if allowed:
        srcs = [s for s in srcs if s in allowed]
    subs = [n for n in (re.sub(r"^/?r/", "", x.strip()).strip("/") for x in (subreddits or SUBREDDITS)) if re.fullmatch(r"\w{2,30}", n)] or SUBREDDITS
    own = client is None
    client = client or httpx.Client(timeout=20, headers={"User-Agent": get_settings().http_user_agent})
    now = time.time() if now is None else now
    now_dt = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    raw, errors, status = [], [], {}
    try:
        for s, res in _parallel(lambda src: _fetch_source(src, client, now, subs), srcs, workers=len(srcs) or 1):
            if isinstance(res, LiveSourceError):
                errors.append(f"{SOURCE_NAMES[s]}: {res}")
                status[s] = {"ok": False, "posts": 0, "name": SOURCE_NAMES[s], "error": str(res)}
                continue
            got, partial = res
            raw += got
            status[s] = {"ok": True, "posts": len(got), "name": SOURCE_NAMES[s], **({"note": "; ".join(partial)} if partial else {})}
    finally:
        if own:
            client.close()
    rows, seen = [], set()
    for p in raw:
        row = _shape(p, qs, now_dt)
        if not row or row["id"] in seen:
            continue
        if max_days and row["age_minutes"] is not None and row["age_minutes"] > max_days * 1440:
            continue          # stale: probably taken already
        seen.add(row["id"])
        rows.append(row)
    rows.sort(key=lambda r: (-r["worth"], r["age_minutes"] or 0))
    keys: set[str] = set()
    per_poster: dict[str, int] = {}
    unique = []
    for r in rows:                    # best-ranked copy of each re-posted ad wins; one account cannot flood the list
        k = _dedupe_key(r)
        if k in keys:
            continue
        if r["poster"]:
            per_poster[r["poster"]] = per_poster.get(r["poster"], 0) + 1
            if per_poster[r["poster"]] > MAX_PER_POSTER:
                continue
        keys.add(k)
        unique.append(r)
    rows = unique
    for st in status.values():
        st["matching"] = 0
    for r in rows:
        status[r["source"]]["matching"] += 1
    if only_email:
        rows = [r for r in rows if r["emails"]]
    if sort == "newest":
        rows.sort(key=lambda r: r["age_minutes"] if r["age_minutes"] is not None else 10 ** 9)
    total = len(rows)
    rows = rows[:max(1, min(limit, 300))]
    emails = [{**e, "post_title": r["title"], "post_url": r["url"], "source_name": r["source_name"]}
              for r in rows for e in r["emails"]]
    return {"queries": qs, "sources": status, "errors": errors, "total_matches": total, "items": rows,
            "emails": emails, "reddit_configured": reddit_configured(), "cached_for_minutes": CACHE_SECONDS // 60,
            "notice": "Read live from Hacker News, client marketplaces, Bluesky, Mastodon, GitHub bounties and remote job "
                      "boards through their public APIs and feeds; nothing is stored. Open each post and reply yourself."}
