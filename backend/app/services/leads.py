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
             "yourname", "user", "username",
             # never an application address, whatever the post says around it
             "accommodation", "accommodations", "accomodations", "reasonableaccommodations", "reasonableaccommodation",
             "accessibility", "ada", "eeo", "compliance", "fraud", "scam", "report", "media", "investors", "investor",
             "support", "help", "billing", "invoices", "payroll", "ap", "ar", "gdpr", "complaints", "trust", "safety"}
BAD_DOMAINS = {"example.com", "example.org", "sentry.io", "wixpress.com", "domain.com", "email.com", "yourcompany.com",
               "yoursite.com", "test.com", "sentry.wixpress.com", "localhost"}
FREEMAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me",
            "protonmail.com", "live.com", "aol.com", "gmx.com", "gmx.net", "yandex.com", "mail.com"}
# Words that mean the address is for something OTHER than applying (accommodation requests, fraud reports, privacy,
# legal ...). Seen on real boards: "If you need an accommodation please contact recruiting@x.com", "report fraud to
# careers@x.com", "contact People Ops at hr@x.com about our Affirmative Action Plan".
NOT_FOR_APPLYING = re.compile(
    r"\b(accommodat\w*|accomodat\w*|disabilit\w*|neurodivers\w*|adjustments?|accessib\w*|fraud\w*|scam\w*|phishing|impersonat\w*|privacy|data protection|"
    r"gdpr|affirmative action|complaint\w*|unsubscribe|opt[- ]?out|subpoena|legal|investor\w*|press (inquir|request|contact)|"
    r"media (inquir|request|contact)|billing|invoice\w*)\b", re.I)
# Wording that clearly invites an application (or a pitch) at an address.
INVITE_RE = re.compile(
    r"\b(to apply|apply (by|via|at|to|here|now|with|directly)|applying|applications?\b.{0,40}\b(to|at|via)|"
    r"send (us |me )?(in )?(your |a |an |the )?(brief |short )?(cv|resume|r[ée]sum[ée]|application|cover letter|intro\w*|note|pitch|portfolio|github)|"
    r"(e-?mail|write) (us|me|your|a|an|to)|resumes? (to|at)|cvs? (to|at)|submit (your|an|a)|express\w* (your )?interest|"
    r"get in touch|reach out|reach (me|us) at|introduce yourself|contact:|apply:|email:|"
    r"(e-?mail|write to|send (it )?to|resumes? to|cvs? to)\s*:?\s*[\w.+-]+@)", re.I)
# contact purposes that exist only for a pitch to a company the user chose; never offered as a job-application address
PITCH_PURPOSES = ("b2b_mailbox", "partner_invited")
CAREER_LOCALS = {"jobs", "job", "careers", "career", "hiring", "recruiting", "recruitment", "talent", "hr", "people",
                 "join", "work", "apply", "freelance", "contractors", "recruiter"}
ROLE_LOCALS = CAREER_LOCALS | {"team", "hello", "contact", "info", "hi", "office", "partners", "partnerships",
                               "business", "bizdev", "projects", "sales", "enquiries", "mail"}


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence (or line) that contains text[start:end]. Whether an address is for applying is judged within
    its own sentence: "Questions: x@y.com" is not an invitation just because "Apply" appears elsewhere nearby."""
    lo = 0
    for m in _SENTENCE_BREAK.finditer(text, 0, start):
        lo = m.end()
    m = _SENTENCE_BREAK.search(text, end)
    hi = m.start() if m else len(text)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def extract_emails(text: str, strict: bool = False) -> list[dict]:
    """Return [{email, invited, context}] for plausible business contact addresses.

    An address whose surrounding text is about something other than applying (accommodation requests, fraud
    reports, privacy, legal ...) is dropped. With strict=True (ordinary job boards) an address is also dropped unless
    the text clearly invites applications there; Hacker News posts, alerts and manual entries are not strict because
    the whole text is the job post."""
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
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 90): m.end() + 60]).strip()
        # ordinary boards carry lots of boilerplate, so look further ahead there than in a Hacker News post
        near = re.sub(r"\s+", " ", text[max(0, m.start() - 110): m.end() + (220 if strict else 50)])
        if NOT_FOR_APPLYING.search(near):
            continue
        invited = bool(INVITE_RE.search(_sentence(text, m.start(), m.end())))
        if strict and not invited:
            continue
        seen.add(low)
        out.append({"email": email, "invited": invited, "context": ctx})
    return out


# People advertising THEMSELVES (the "Who wants to be hired?" template, posted by mistake in the hiring thread).
# They are not clients and their personal addresses must never be collected.
JOB_SEEKER_POST = re.compile(r"(willing to relocate\s*:|r[ée]sum[ée]\s*/\s*cv\s*:|\bseeking work\b|\bavailable for (hire|freelance work)\b)", re.I)


def is_job_seeker_post(text: str) -> bool:
    return bool(JOB_SEEKER_POST.search(text or ""))


def _suppressed(db: Session, norm: str) -> bool:
    dom = norm.split("@")[-1]
    return db.scalar(select(Suppression.id).where((Suppression.email_norm == norm) | (Suppression.domain == dom)).limit(1)) is not None


# The basis texts classify() writes itself. Eligibility you set by hand carries your own basis, so it is never rewritten.
AUTO_BASIS_PREFIXES = ("The hiring company published this address", "Published in the listing for applications",
                       "Address appears in the listing", "Careers/jobs mailbox published", "General business mailbox published",
                       "The company's own website invites", "Public business mailbox on the company's website")


# A sentence on a company's own site that invites freelancers or contractors to get in touch. Deliberately narrow:
# "Freelancers: weak governance ...", "Looking for a freelancer? Hire our team", "We are a long-term partner. Contact us"
# and reseller pages ("Become a partner") are NOT invitations. A missed invitation only means "review"; a wrong one
# would promise permission that does not exist.
_FW = (r"(?:freelanc\w*|contractors?|subcontract\w*|independent (?:consultants?|engineers?|developers?|experts?)|"
       r"external (?:experts?|specialists?|engineers?|developers?)|talent (?:pool|network))")
PARTNER_INVITE = re.compile(
    r"\b(?:we(?:'re| are)?|our)\b[^.!?\n]{0,40}\b(?:looking for|hiring|seeking|recruiting|welcome|invite|open to)\b[^.!?\n]{0,60}\b" + _FW + r"\b"
    r"|\b(?:join|become|apply (?:as|to join)|work with)\b[^.!?\n]{0,30}\b(?:our|us|a|an)\b[^.!?\n]{0,40}\b" + _FW + r"\b"
    r"|\b" + _FW + r"\b[^.!?\n]{0,40}\b(?:can|may|should|please|are welcome to|wanted|welcome)\b[^.!?\n]{0,50}"
    r"\b(?:contact|e-?mail|write|reach|apply|send|get in touch)\b", re.I)
_NEGATED = re.compile(r"\b(not|never|no|don't|doesn't|do not|does not|without|won't|cannot|can't)\b", re.I)


def invites_freelancers(text: str) -> bool:
    """True when some sentence of `text` (a page of the company's own site) invites freelancers/contractors.
    Questions ("Looking for a freelancer?") are marketing aimed at clients, and negated sentences are skipped."""
    for m in re.finditer(r"[^.!?\n]+[.!?]?", text or ""):
        sent = m.group(0).strip()
        if sent.endswith("?") or _NEGATED.search(sent):
            continue
        if PARTNER_INVITE.search(sent):
            return True
    return False


# A sentence on a company's own site that asks people to send an application to an address. Narrower than INVITE_RE on
# purpose: "Contact: x@y.com" and "Email: x@y.com" are labels, not invitations.
APPLY_INVITE = re.compile(
    r"\b(to apply|apply (by|via|at|with|directly)|"
    r"send (us |me )?(in )?(your |a |an |the )?(brief |short |updated )?(cv|resume|r[ée]sum[ée]|application|cover letter|portfolio)|"
    r"(cvs?|r[ée]sum[ée]s?|applications?) (to|at)|submit (your|an|a) (cv|resume|r[ée]sum[ée]|application))\b", re.I)


def _invites_at(text: str, start: int, end: int, pattern: re.Pattern = PARTNER_INVITE) -> bool:
    """The sentence holding the address matches `pattern`. The address itself is blanked first so that a mailbox
    called partners@ or freelance@ cannot invite on its own behalf."""
    sent = _sentence(text, start, end)
    sent = sent.replace(text[start:end], " ")
    return not _NEGATED.search(sent) and bool(pattern.search(sent))


def classify(email: str, invited: bool, origin: str, mode: str = "application") -> tuple[str, str, str]:
    """origin: 'listing' (company's hiring post/listing) or 'website'. mode: 'application' (the person is applying)
    or 'pitch' (an unsolicited B2B message to a company). -> (purpose, eligibility, basis)"""
    local, domain = email.lower().split("@", 1)
    free = domain in FREEMAIL
    if mode == "pitch" and origin == "website":
        if invited and not free:
            return ("partner_invited", "eligible",
                    "The company's own website invites freelancers/partners to contact it at this address. Use it only for that purpose.")
        return ("b2b_mailbox", "review_required",
                "Public business mailbox on the company's website. A pitch is unsolicited: check the rules for the recipient's "
                "country, identify yourself and give a way to opt out. Prefer a contact form if the company offers one.")
    if origin == "website" and invited and not free:
        return ("careers_mailbox" if local.split("+")[0] in CAREER_LOCALS else "application_invited", "eligible",
                "The company's own website invites applications at this address. Use it only for that purpose.")
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
                  only_role_on_domain: str = "", now: datetime | None = None, strict: bool = False,
                  mode: str = "application") -> list[BusinessContact]:
    """Create/update BusinessContact rows (with provenance) for emails found in `text`."""
    now = now or utcnow()
    found = []
    for item in extract_emails(text, strict=strict):
        email = item["email"]
        local, domain = email.lower().split("@", 1)
        if only_role_on_domain:  # website scan: same company domain and role mailboxes only (data minimisation)
            d = only_role_on_domain.lower()
            if not (domain == d or domain.endswith("." + d) or d.endswith("." + domain)):
                continue
            if local.split("+")[0] not in ROLE_LOCALS:
                continue
        if origin == "website":   # on a company site only an explicit invitation counts
            pos = text.find(email)
            invited = _invites_at(text, pos, pos + len(email))    # ... freelancers/contractors may get in touch here
            if mode == "application" and not invited:             # ... or, when you are applying: send your CV/application here
                invited = _invites_at(text, pos, pos + len(email), APPLY_INVITE)
        else:
            invited = item["invited"]
        purpose, elig, basis = classify(email, invited, origin, mode)
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
            elif (origin == "website" and c.source_type == "company_website" and c.opportunity_id in (None, opp.id) and not c.suppressed
                  and (c.eligibility_basis or "").startswith(AUTO_BASIS_PREFIXES) and (purpose, elig) != (c.contact_purpose, c.outreach_eligibility)):
                c.contact_purpose, c.outreach_eligibility, c.eligibility_basis = purpose, elig, basis     # the rules improved: refresh our own decision
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


# ---------------------------------------------------------------- clean-up of contacts found by older, looser rules


def _board_listing(source_key: str) -> bool:
    return source_key not in ("hn_hiring", "manual") and not source_key.startswith("alert_")


def reclassify_contacts(db: Session) -> dict:
    """Re-judge every address the app found by itself (hiring posts / company websites) with the current rules.
    Addresses that are not for applying (accommodation, fraud, privacy ...) are deleted; the rest keep their
    provenance. Contacts you added yourself, and eligibility you set by hand, are never touched."""
    removed = kept = changed = 0
    for c in db.scalars(select(BusinessContact).where(BusinessContact.source_type.in_(("hiring_post", "company_website")))).all():
        opp = db.get(Opportunity, c.opportunity_id) if c.opportunity_id else None
        strict = c.source_type == "hiring_post" and opp is not None and _board_listing(opp.source_key)
        found: list[dict] = []
        if c.source_type == "hiring_post":
            # judge with the whole listing text when we have it (the stored snippet is short)
            text = opp.description if opp is not None and c.email_norm in (opp.description or "").lower() else \
                (c.source_note if c.email_norm in c.source_note.lower() else f"{c.source_note} {c.email}")
            found = extract_emails(text, strict=strict)
            ok = any(f["email"].lower() == c.email_norm for f in found)
        else:
            ok = c.email_norm.split("@")[0].split("+")[0] not in BAD_LOCAL and not NOT_FOR_APPLYING.search(c.source_note or "")
        if not ok:
            db.delete(c)
            removed += 1
            continue
        kept += 1
        if c.source_type == "hiring_post" and (c.eligibility_basis or "").startswith(AUTO_BASIS_PREFIXES):
            invited = any(f["email"].lower() == c.email_norm and f["invited"] for f in found)
            purpose, elig, basis = classify(c.email, invited, "listing")
            if (purpose, elig) != (c.contact_purpose, c.outreach_eligibility) and not c.suppressed:
                c.contact_purpose, c.outreach_eligibility, c.eligibility_basis = purpose, elig, basis
                changed += 1
    db.commit()
    return {"removed": removed, "kept": kept, "reclassified": changed}


def refresh_ease(db: Session) -> int:
    """Recompute 'easy to reach' and the apply method from the contacts that survive the clean-up."""
    from ..scoring import effective_geo
    n = 0
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key != "prospect")).all():
        has_email = db.scalar(select(BusinessContact.id).where(
            BusinessContact.opportunity_id == o.id, BusinessContact.suppressed.is_(False),
            BusinessContact.contact_purpose.in_(("application_invited", "application_invited_freemail", "careers_mailbox"))).limit(1)) is not None
        score, signals, method = compute_ease(o.title, o.description, o.engagement_type, effective_geo(o.location_requirements, o.description),
                                              o.posted_at, has_email)
        if (round(score, 1), signals, method) != (round(o.ease_score or 0, 1), list(o.ease_signals or []), o.apply_method):
            o.ease_score, o.ease_signals, o.apply_method = score, signals, method
            if method != "email" and (o.recommended_action or "").startswith("Email your application"):
                o.recommended_action = "Worth a look: read the full listing"
            n += 1
    db.commit()
    return n


# A hiring post whose header was edited to say it is closed ("CLOSED NOW", "[CLOSED]", "position filled").
CLOSED_POST = re.compile(r"\bclosed now\b|\bnow closed\b|\bno longer (hiring|accepting|taking)\b|"
                         r"\b(position|role|job)s? (has been |have been |is |are |was |were )?(filled|closed)\b|[\[(|]\s*closed\s*(?:[\])|:\-–—]|$)|^\s*closed\b", re.I)


def close_stale_posts(db: Session) -> int:
    """Mark hiring posts that say they are closed as closed, so they are not offered as leads. Nothing is deleted."""
    n = 0
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key == "hn_hiring", Opportunity.listing_status != "closed")).all():
        if CLOSED_POST.search((o.description or "")[:300]):
            o.listing_status = "closed"
            n += 1
    db.commit()
    return n


def purge_job_seeker_posts(db: Session) -> dict:
    """Remove job-seeker posts (and their contacts) that older rules ingested as if they were job offers.
    A post that already has an application recorded is left alone."""
    from sqlalchemy import delete, update
    from ..models import Application, Evidence, OpportunityHistory, ProposalDraft, RunOpportunity
    applied = set(db.scalars(select(Application.opportunity_id)).all())
    ids = [o.id for o in db.scalars(select(Opportunity).where(Opportunity.source_key == "hn_hiring")).all()
           if is_job_seeker_post(o.description) and o.id not in applied]
    if not ids:
        return {"posts": 0, "contacts": 0}
    contacts = db.execute(delete(BusinessContact).where(BusinessContact.opportunity_id.in_(ids))).rowcount
    db.execute(update(Evidence).where(Evidence.opportunity_id.in_(ids)).values(opportunity_id=None))   # company facts stay
    for model in (RunOpportunity, OpportunityHistory, ProposalDraft):
        db.execute(delete(model).where(model.opportunity_id.in_(ids)))
    db.execute(delete(Opportunity).where(Opportunity.id.in_(ids)))
    db.commit()
    return {"posts": len(ids), "contacts": contacts}
