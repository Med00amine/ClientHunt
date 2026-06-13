"""Hiring-contact discovery and the 'easy to reach' signal.

Emails are only taken from text the company itself published (its hiring post or its own website),
never guessed, never taken from Upwork/Fiverr profiles. Every contact keeps its source URL, date and a
snippet of the surrounding text. Eligibility is conservative:
  eligible         the company invited applications at this address (hiring post) or published a careers/jobs
                   mailbox on its own site. Intended use: send a job application / project inquiry only.
  review_required  general business mailbox, free-mail address, or an address with no invitation text.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BusinessContact, Opportunity, Suppression, utcnow
from ..textutil import norm_text

EMAIL_RE = re.compile(r"(?<![\w.+%-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}(?![\w-])")
BAD_LOCAL = {"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster", "abuse", "privacy",
             "legal", "dpo", "security", "unsubscribe", "press", "sentry", "example", "test", "name", "email", "you",
             "yourname", "user", "username"}
BAD_DOMAINS = {"example.com", "example.org", "sentry.io", "wixpress.com", "domain.com", "email.com", "yourcompany.com",
               "yoursite.com", "test.com", "sentry.wixpress.com", "localhost"}
FREEMAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me",
            "protonmail.com", "live.com", "aol.com", "gmx.com", "gmx.net", "yandex.com", "mail.com"}
INVITE_RE = re.compile(r"\b(apply|applying|application|applications|resume|résumé|cv|cover letter|e-?mail|send|reach out|"
                       r"get in touch|interested|contact|questions|introduce|pitch|mention)\b", re.I)
CAREER_LOCALS = {"jobs", "job", "careers", "career", "hiring", "recruiting", "recruitment", "talent", "hr", "people",
                 "join", "work", "apply", "freelance", "contractors", "recruiter"}
ROLE_LOCALS = CAREER_LOCALS | {"team", "hello", "contact", "info", "hi", "office", "partners", "partnerships",
                               "business", "bizdev", "projects", "sales", "enquiries", "mail"}


def extract_emails(text: str) -> list[dict]:
    """Return [{email, invited, context}] for syntactically valid, plausible business contact addresses."""
    out, seen = [], set()
    for m in EMAIL_RE.finditer(text or ""):
        email = m.group(0).rstrip(".")
        low = email.lower()
        local, domain = low.split("@", 1)
        base_local = local.split("+")[0]
        if base_local in BAD_LOCAL or domain in BAD_DOMAINS or re.search(r"\.(png|jpe?g|gif|svg|webp)$", domain):
            continue
        if low in seen:
            continue
        seen.add(low)
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 90): m.end() + 60]).strip()
        out.append({"email": email, "invited": bool(INVITE_RE.search(ctx)), "context": ctx})
    return out


def _suppressed(db: Session, norm: str) -> bool:
    dom = norm.split("@")[-1]
    return db.scalar(select(Suppression.id).where((Suppression.email_norm == norm) | (Suppression.domain == dom)).limit(1)) is not None


def classify(email: str, invited: bool, origin: str) -> tuple[str, str, str]:
    """origin: 'listing' (company's hiring post/listing) or 'website'. -> (purpose, eligibility, basis)"""
    local, domain = email.lower().split("@", 1)
    free = domain in FREEMAIL
    if origin == "listing":
        if invited and not free:
            return ("application_invited", "eligible",
                    "The hiring company published this address in its own listing to receive applications. "
                    "Use it only to apply for that role / ask about it.")
        if invited and free:
            return ("application_invited_freemail", "review_required",
                    "Published in the listing for applications, but it is a free-mail address (an individual). Check before use.")
        return ("listing_mentioned", "review_required", "Address appears in the listing without clear application wording.")
    base = local.split("+")[0]
    if base in CAREER_LOCALS:
        return ("careers_mailbox", "eligible",
                "Careers/jobs mailbox published on the company's own website. Use it only for a job application or project inquiry.")
    return ("general_business_contact", "review_required",
            "General business mailbox published on the company's website. Check the rules for the recipient's country before writing.")


def attach_emails(db: Session, opp: Opportunity, text: str, origin: str = "listing", source_url: str = "",
                  only_role_on_domain: str = "", now: datetime | None = None) -> list[BusinessContact]:
    """Create/update BusinessContact rows (with provenance) for emails found in `text`."""
    now = now or utcnow()
    found = []
    for item in extract_emails(text):
        email = item["email"]
        local, domain = email.lower().split("@", 1)
        if only_role_on_domain:  # website scan: same company domain and role mailboxes only (data minimisation)
            d = only_role_on_domain.lower()
            if not (domain == d or domain.endswith("." + d) or d.endswith("." + domain)):
                continue
            if local.split("+")[0] not in ROLE_LOCALS:
                continue
        purpose, elig, basis = classify(email, item["invited"], origin)
        norm = email.strip().lower()
        c = db.scalar(select(BusinessContact).where(BusinessContact.email_norm == norm))
        src = source_url or opp.original_url
        if c is None:
            c = BusinessContact(
                email=email.strip(), email_norm=norm, domain=domain, name="", company_name=opp.company_name,
                company_id=opp.company_id, is_generic=local.split("+")[0] in ROLE_LOCALS,
                role="careers / hiring address" if local.split("+")[0] in CAREER_LOCALS else "",
                source_type="hiring_post" if origin == "listing" else "company_website", source_url=src,
                source_note=item["context"][:300], retrieved_at=now, verified_status="unverified",
                outreach_eligibility=elig, eligibility_basis=basis, opportunity_id=opp.id, contact_purpose=purpose,
                suppressed=_suppressed(db, norm))
            if c.suppressed:
                c.outreach_eligibility = "not_eligible"
            db.add(c)
        else:
            if not c.source_url:  # previously stored without provenance: now we have a real source
                c.source_url, c.source_note, c.retrieved_at = src, item["context"][:300], now
                c.source_type = "hiring_post" if origin == "listing" else "company_website"
                c.contact_purpose, c.eligibility_basis = purpose, basis
                if not c.suppressed and c.outreach_eligibility in ("unknown", "review_required"):
                    c.outreach_eligibility = elig
            if c.opportunity_id is None:
                c.opportunity_id = opp.id
            if c.company_id is None and opp.company_id:
                c.company_id = opp.company_id
        found.append(c)
    db.flush()
    return found


# ---------------------------------------------------------------- hiring ease
_URGENT = re.compile(r"\b(asap|as soon as possible|immediate(ly)?( start)?|urgent(ly)?|start(ing)? (right )?(now|away)|"
                     r"available now|hiring now|open now)\b", re.I)
_CONTRACT = re.compile(r"\b(contract|contractor|freelance|freelancer|part[- ]time|short[- ]term|project[- ]based|"
                       r"consultant|consulting)\b", re.I)
_SMALL = re.compile(r"\b(early[- ]stage|seed|pre-seed|founding|small team|startup|start-up|series a)\b", re.I)
_MULTI = re.compile(r"\b(multiple|several|many) (roles|openings|positions|engineers)|\bhiring \d+\b", re.I)
_NO_CONTRACT = re.compile(r"\bno (contractors?|freelancers?|agencies|agency|c2c|third[- ]part(y|ies)|recruiters?)\b", re.I)
_LOCAL_ONLY = re.compile(r"\b(onsite|on-site|on site|must (be located|reside|live)|authorized to work in the (us|u\.s\.|uk)|"
                         r"no visa|visa sponsorship (is )?not|work authorization required|us citizens? only|"
                         r"must be (based|located) in)\b", re.I)


def compute_ease(title: str, description: str, engagement_type: str, geo: str, posted_at, has_email: bool,
                 now: datetime | None = None) -> tuple[float, list[str], str]:
    """Heuristic 0-100: how low-friction it looks to reach the client and be considered. NOT a hiring prediction.
    Returns (score, signals, apply_method)."""
    now = now or utcnow()
    blob = f"{title}\n{description}"
    pts: list[tuple[int, str]] = []
    if has_email:
        pts.append((30, "Company published an email to apply (+30)"))
    if engagement_type in ("contract", "freelance", "part_time") or _CONTRACT.search(blob):
        pts.append((20, "Contract / freelance / part-time wording (+20)"))
    if geo == "worldwide":
        pts.append((15, "Open to any location (+15)"))
    elif geo == "compatible":
        pts.append((8, "Location looks Europe/Africa-compatible (+8)"))
    if posted_at:
        age = (now - posted_at).days
        if age <= 7:
            pts.append((10, "Posted in the last 7 days (+10)"))
        elif age <= 14:
            pts.append((5, "Posted in the last 14 days (+5)"))
    if _URGENT.search(blob):
        pts.append((10, "Wants someone soon / urgent (+10)"))
    if _SMALL.search(blob):
        pts.append((5, "Small / early-stage team, usually fewer hiring steps (+5)"))
    if _MULTI.search(blob):
        pts.append((5, "Several openings (+5)"))
    if _NO_CONTRACT.search(blob):
        pts.append((-25, "Says no contractors/agencies/recruiters (−25)"))
    if geo == "restricted" or _LOCAL_ONLY.search(blob):
        pts.append((-20, "Location/work-authorisation restriction may exclude you (−20)"))
    score = max(0.0, min(100.0, float(sum(p for p, _ in pts))))
    method = "email" if has_email else "link"
    return score, [t for _, t in pts], method
