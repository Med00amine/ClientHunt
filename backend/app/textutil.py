import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source",
             "fbclid", "gclid", "ref_src"}


def html_to_text(html: str, limit: int = 8000) -> str:
    """Untrusted HTML -> plain text. Scripts/styles dropped; nothing is executed or followed."""
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style", "noscript", "iframe"]):
        t.decompose()
    for a in soup.find_all("a", href=True):  # keep mailto: addresses that get_text() would drop
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr and addr.lower() not in a.get_text().lower():
                a.append(f" {addr}")
    for el in soup.find_all(["br", "p", "li", "div", "h1", "h2", "h3"]):
        if el.name != "br":
            el.insert(0, "\n")  # unclosed <p> tags nest in html.parser: break before each block, not only after
        el.append("\n")
    text = soup.get_text(" ")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:limit]


def canonical_url(url: str) -> str:
    try:
        p = urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(sorted(q)), ""))


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fingerprint(company: str, title: str, description: str) -> str:
    """Cautious content fingerprint: company + full normalised title + start of description.
    Similar-but-different titles do NOT collide."""
    basis = "|".join([norm_text(company), norm_text(title), norm_text(description)[:600]])
    return hashlib.sha256(basis.encode()).hexdigest()


def content_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode()).hexdigest()


_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralise spreadsheet formula injection in user-controlled strings."""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip(" ")
    if stripped.startswith(_FORMULA) or value.startswith(_FORMULA):
        return "'" + value
    return value
