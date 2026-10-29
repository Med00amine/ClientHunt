"""Turn free text (a hiring post, a pasted email thread, a web page) into rows of Name / Email / Company.

Only addresses written in the text are returned: nothing is guessed. The name and the company are read from the
text around the address ("Jane Doe <jane@acme.io>", "contact Jane at ...", a signature line) or, failing that, from
the address itself, and every row says where its name and company came from, so a guess is never shown as a fact."""
from __future__ import annotations

import re

from .leads import FREEMAIL, ROLE_LOCALS, extract_emails

_WORD = r"[A-Z][a-zA-Z'’-]+"
_NAME = rf"{_WORD}(?:\s+(?:[A-Z]\.|{_WORD})){{0,3}}"
# "Jane Doe <jane@x.com>", "Jane Doe (jane@x.com)", "Jane Doe - jane@x.com", "Jane Doe: jane@x.com"
_NAME_BEFORE = re.compile(rf"({_NAME})\s*(?:<|\(|\[|[-–—:,]|\bat\b|\bon\b)?\s*$")
# "contact Jane at", "email Jane Doe via", "reach out to Jane at"
_NAME_VERB = re.compile(rf"\b(?:contact|e-?mail|ping|message|reach(?: out to)?|write to|send (?:it|them|your \w+) to|ask for)\s+({_NAME})\s+(?:at|on|via|by)\s*:?\s*$", re.I)
_NOT_NAME = {"Email", "E-mail", "Mail", "Contact", "Apply", "Send", "Reach", "Write", "Questions", "Resume", "Resumes",
             "Cv", "CV", "Please", "To", "At", "Or", "And", "The", "Us", "Me", "Hiring", "Remote", "Interested", "If",
             "Dm", "DM", "Pm", "PM", "Reply", "Thanks", "Thank", "Cheers", "Regards", "Best", "Note", "Jobs", "Careers"}
# mailboxes named after a job title or a team, not a person
_TITLE_LOCALS = {"ceo", "cto", "coo", "cfo", "cpo", "founder", "founders", "cofounder", "owner", "dev", "devs", "engineering",
                 "tech", "product", "design", "ops", "operations", "founders.team", "recruit", "staffing", "admin"}
_COMPANY_LABEL = re.compile(r"^\s*(?:company|employer|organisation|organization|client|agency)\s*[:\-–]\s*(.{2,80})$", re.I | re.M)
_COMPANY_IN_LINE = re.compile(r"\b(?:at|from|with|@)\s+([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3})\s*$")
_SUFFIX = re.compile(r"\.(co\.uk|com\.au|co\.za|co|com|io|ai|dev|app|net|org|tech|so|xyz|us|uk|de|fr|tn|ca|eu|me|inc|ly)$", re.I)


def _clean_name(raw: str) -> str:
    words = [w for w in raw.split() if w not in _NOT_NAME]
    while words and words[0] in _NOT_NAME:
        words.pop(0)
    return " ".join(words[:4]) if words and all(w[0].isupper() for w in words) else ""


def _name_near(text: str, start: int) -> str:
    before = text[max(0, start - 60):start]
    before = before.split("\n")[-1]
    for rx in (_NAME_VERB, _NAME_BEFORE):
        m = rx.search(before)
        if m:
            name = _clean_name(m.group(1))
            if name:
                return name
    return ""


def _name_from_address(email: str) -> str:
    local = email.split("@", 1)[0].split("+")[0].lower()
    if local in ROLE_LOCALS or local in _TITLE_LOCALS:
        return ""
    parts = [p for p in re.split(r"[._-]", local) if p.isalpha() and len(p) > 1]
    return " ".join(p.capitalize() for p in parts[:3]) if 1 <= len(parts) <= 3 else ""


def _company_from_domain(domain: str) -> str:
    if domain in FREEMAIL:
        return ""
    host = domain.lower()
    for _ in range(2):
        host = _SUFFIX.sub("", host)
    label = host.split(".")[-1]
    return " ".join(p.capitalize() for p in re.split(r"[-_]", label) if p)


def contact_rows(text: str, company: str = "", poster: str = "") -> list[dict]:
    """[{name, email, company, name_from, company_from, invited, context}] for every usable address in `text`.

    `company` is a company already known for the whole text (e.g. a post header); `poster` is the account that
    published it (e.g. a Reddit username), used as the name only when the text names nobody."""
    text = text or ""
    labelled = _COMPANY_LABEL.search(text)
    out = []
    for item in extract_emails(text):
        email = item["email"]
        pos = text.find(email)
        name, name_from = _name_near(text, pos), "text"
        if not name:
            name, name_from = _name_from_address(email), "address"
        if not name and poster:
            name, name_from = poster, "poster"
        if not name:
            name_from = ""
        comp, comp_from = company.strip(), "post"
        if not comp and labelled:
            comp, comp_from = labelled.group(1).split("|")[0].strip(), "text"
        if not comp:
            line = text[max(0, pos - 80):pos].split("\n")[-1]
            m = _COMPANY_IN_LINE.search(line)
            comp, comp_from = (m.group(1).strip(), "text") if m and m.group(1) not in _NOT_NAME else ("", "")
        if not comp:
            comp = _company_from_domain(email.split("@", 1)[1].lower())
            comp_from = "domain" if comp else ""
        out.append({"name": name, "email": email, "company": comp[:120], "name_from": name_from,
                    "company_from": comp_from, "invited": item["invited"], "context": item["context"]})
    return out
