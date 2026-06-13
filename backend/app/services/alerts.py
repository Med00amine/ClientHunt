"""Parse pasted/uploaded job-alert emails (e.g. Upwork saved-search notifications) locally.
No network access; links are preserved, text is untrusted."""
from __future__ import annotations

import email
import re
from datetime import datetime
from email import policy
from email.utils import parsedate_to_datetime

from ..textutil import html_to_text
from ..types import RawOpportunity

_URL = re.compile(r"https?://[^\s<>\"')\]]+")
_JOB_URL = {
    "upwork": re.compile(r"upwork\.com/(jobs|freelance-jobs/apply|nx/proposals/job)/[^\s<>\"')\]]*", re.I),
    "contra": re.compile(r"contra\.com/opportunity/[^\s<>\"')\]]*", re.I),
    "peopleperhour": re.compile(r"peopleperhour\.com/freelance-jobs/[^\s<>\"')\]]*", re.I),
    "guru": re.compile(r"guru\.com/jobs/[^\s<>\"')\]]*", re.I),
    "freelancer": re.compile(r"freelancer\.com/projects/[^\s<>\"')\]]*", re.I),
    "wellfound": re.compile(r"wellfound\.com/(jobs|company)/[^\s<>\"')\]]*", re.I),
}


def parse_alert(raw_text: str, platform_hint: str = "") -> list[RawOpportunity]:
    """Accepts either a raw RFC822 message or plain pasted text/HTML. One opportunity per job link found."""
    body, received = raw_text, None
    if re.match(r"^(From|Received|Return-Path|Subject|MIME-Version):", raw_text.lstrip(), re.I | re.M):
        msg = email.message_from_string(raw_text, policy=policy.default)
        try:
            received = parsedate_to_datetime(msg["Date"]).replace(tzinfo=None) if msg["Date"] else None
        except (TypeError, ValueError):
            received = None
        part = msg.get_body(preferencelist=("html", "plain"))
        body = part.get_content() if part else ""
    is_html = "<a " in body.lower() or "<html" in body.lower()
    links: list[tuple[str, str]] = []
    if is_html:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body, "html.parser")
        for a in soup.find_all("a", href=True):
            links.append((a["href"], a.get_text(" ", strip=True)))
        text = html_to_text(body, 20000)
    else:
        text = body
        links = [(u, "") for u in _URL.findall(body)]
    out, seen = [], set()
    for href, label in links:
        platform = platform_hint
        for plat, pat in _JOB_URL.items():
            if pat.search(href):
                platform = plat
                break
        else:
            if not platform_hint:
                continue
        url = href.split("?")[0] if platform == "upwork" else href
        if url in seen:
            continue
        seen.add(url)
        title = label if len(label) > 8 and not label.lower().startswith(("view", "apply", "http")) else ""
        if not title:
            idx = text.find(href)
            window = text[max(0, idx - 160):idx] if idx > 0 else ""
            title = (window.strip().splitlines() or [""])[-1][:200]
        if not title:
            title = "Job alert item (open link to read details)"
        anchor = text.find(label) if label else -1
        if anchor < 0:
            anchor = text.find(href)
        window = text[max(0, anchor - 100): anchor + 900] if anchor >= 0 else text[:1000]
        out.append(RawOpportunity(source_key=f"alert_{platform or 'other'}", url=url, title=title[:300],
                                  description=window, posted_at=received, remote_status="unknown",
                                  source_type="alert"))
    return out
