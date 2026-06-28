"""Prospects: companies YOU choose to approach (agencies that may subcontract, companies that may need something
built, networks to join). The app reads the company's OWN public website (robots.txt respected), keeps verbatim
evidence, finds the role mailboxes the company published (with source URL and date) and prepares a pitch you review.
Nothing is emailed. A prospect is an Opportunity with source_key='prospect' so drafts, applications and the pipeline
work unchanged; it is kept out of the job lists, lead counts and runs."""
from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ..models import (Application, BusinessContact, Company, Evidence, Opportunity, OpportunityHistory, ProposalDraft,
                      utcnow)
from ..scoring import score
from ..textutil import norm_text
from ..types import RawOpportunity
from . import leads, research
from .safefetch import SafeFetcher

SOURCE = "prospect"

OFFERS: dict[str, dict] = {
    "rag_assistant": {
        "label": "Question-answering assistant over your own documents (RAG)",
        "audience": "Teams with many PDFs, manuals, tickets or policies that people keep searching by hand.",
        "pitch": "I build question-answering assistants over a company's own documents (Python, FastAPI, vector search, AWS), "
                 "usually as a small fixed-scope pilot you can judge on your own questions.",
        "ask": "If it is useful, I can send a one-page outline of how I would build a pilot on your documents, with a realistic estimate.",
        "deliverable": "A working pilot behind an API or a simple page, a test set of real questions, and a short report on what it gets right and wrong.",
        "first_step": "A 30-minute call to choose about 20 real questions and the documents they should be answered from.",
        "skills": ["rag", "llm", "python", "fastapi", "aws", "docker"],
        "keywords": r"\b(documents?|pdfs?|knowledge base|manuals?|policies|tickets?|support|faq|search|assistant|chatbot)\b",
    },
    "document_extraction": {
        "label": "Document processing: turn PDFs and forms into structured data",
        "audience": "Companies that re-type invoices, contracts, forms or reports into other systems.",
        "pitch": "I build document-processing pipelines that turn PDFs, scans and forms into structured data, with validation "
                 "and a review step for low-confidence results (Python, FastAPI, AWS).",
        "ask": "If you handle documents like this, I can send a short outline of how I would automate one document type end to end.",
        "deliverable": "A pipeline for one document type with field validation, an error report and a review queue for uncertain results.",
        "first_step": "Send me 20 sample documents (anonymised) and I tell you what can be automated and how reliably.",
        "skills": ["document processing", "python", "fastapi", "aws", "workflow automation"],
        "keywords": r"\b(invoices?|forms?|ocr|scans?|contracts?|claims?|paperwork|receipts?|extraction|reports?)\b",
    },
    "aws_deployment": {
        "label": "Deploy and run a model or API on AWS",
        "audience": "Teams with a working notebook, model or service that is not yet in production.",
        "pitch": "I containerise ML and LLM services and deploy them on AWS with CI, tests and basic monitoring, "
                 "so what works on a laptop runs reliably in production.",
        "ask": "If you have something waiting to go live, I can send a short plan with the steps and an estimate.",
        "deliverable": "A repeatable deployment (container, CI pipeline, environment configuration) and a short runbook.",
        "first_step": "A short call to review what exists and what production needs.",
        "skills": ["aws", "docker", "ci/cd", "python", "machine learning", "testing"],
        "keywords": r"\b(cloud|aws|devops|deploy\w*|infrastructure|kubernetes|docker|migration|serverless)\b",
    },
    "workflow_automation": {
        "label": "Automate a manual workflow and connect your tools",
        "audience": "Operations teams doing repetitive work between several systems.",
        "pitch": "I automate manual workflows and connect tools through their APIs and webhooks (Python, FastAPI), "
                 "starting with the one process that costs your team the most time.",
        "ask": "If a process comes to mind, I can send a short outline of how I would automate it and what it would take.",
        "deliverable": "One automated workflow with logging, error handling and a manual override.",
        "first_step": "Walk me through the current steps once; I map them and propose what to automate first.",
        "skills": ["workflow automation", "api integration", "python", "fastapi", "testing"],
        "keywords": r"\b(automat\w+|workflow|integrations?|api|apis|webhooks?|zapier|n8n|manual|operations)\b",
    },
    "ml_prototype": {
        "label": "Machine-learning prototype with a clear success metric",
        "audience": "Teams that think data could help but have not tested it.",
        "pitch": "I build machine-learning prototypes (Python, PyTorch) with a clear metric agreed up front, "
                 "so you learn quickly whether the idea works before investing in a full build.",
        "ask": "If you have data and a question, I can send a short outline of how I would test it and what the first result would show.",
        "deliverable": "A baseline model, an evaluation against your metric and a clear recommendation.",
        "first_step": "A short call to define the question, the data and the metric.",
        "skills": ["machine learning", "pytorch", "python", "nlp"],
        "keywords": r"\b(forecast\w*|predict\w*|classif\w*|recommend\w*|vision|nlp|models?|data science|analytics)\b",
    },
    "subcontract_capacity": {
        "label": "Extra delivery capacity for an agency or consultancy",
        "audience": "Agencies and consultancies that sell Python, AI or AWS delivery and sometimes need extra hands.",
        "pitch": "I am an AI and AWS engineer available as extra delivery capacity for agencies: Python, FastAPI, LLM/RAG work, "
                 "document processing and AWS deployment, remote and with flexible hours.",
        "ask": "If you sometimes need extra capacity on a project, I can send a short profile with examples of my work and my availability.",
        "deliverable": "Well-scoped tasks or a module inside your project, delivered through your process and tools.",
        "first_step": "A short intro call and one small paid task to check the fit on both sides.",
        "skills": ["python", "fastapi", "llm", "rag", "aws", "docker", "document processing", "testing"],
        "keywords": r"\b(agency|consultancy|outsourc\w+|nearshore|staff augmentation|dedicated teams?|white[- ]label|delivery)\b",
    },
    "network_application": {
        "label": "Application to join a network or marketplace",
        "audience": "Vetted networks and marketplaces that bring clients to you.",
        "pitch": "I would like to join your network as an AI and AWS engineer. My core skills are Python, FastAPI, machine learning "
                 "(PyTorch), LLM and RAG applications, document processing and AWS/Docker deployment.",
        "ask": "I can share my profile and examples of my work, and I am happy to take any screening you require.",
        "deliverable": "A complete profile with verified portfolio links, availability and a rate that matches the platform.",
        "first_step": "Complete their application and screening.",
        "skills": ["python", "machine learning", "llm", "rag", "fastapi", "aws", "docker"],
        "keywords": r"\b(network|marketplace|talent|vetted|freelanc\w+)\b",
    },
}
CATEGORIES = {
    "company": {"label": "Company that may need something built", "offer": "rag_assistant"},
    "agency": {"label": "Agency or firm that may subcontract", "offer": "subcontract_capacity"},
    "network": {"label": "Network or marketplace to join", "offer": "network_application"},
}
STATUSES_DONE = ("done", "no_evidence")

# public signals (not proof) that a company may need this kind of work
_SIGNALS = [
    (r"\b(ai|artificial intelligence|machine learning|llm|generative ai)\b", 20, "Public site mentions AI / machine learning"),
    (r"\b(automat\w+|workflow|integrations?|apis?)\b", 15, "Mentions automation, integrations or APIs"),
    (r"\b(aws|amazon web services|cloud|devops)\b", 10, "Mentions cloud / AWS"),
    (r"\b(staff augmentation|dedicated teams?|nearshore|outsourc\w+|white[- ]label|managed delivery)\b", 15,
     "Sells delivery capacity (may need extra hands)"),
]


def normalize_site(url: str) -> str:
    """-> 'https://host'. Only public http(s) websites; no credentials, no private or local addresses."""
    u = (url or "").strip()
    if not u or any(c in u for c in " \t\n\r<>\"'"):
        raise ValueError("Enter one public website address, for example https://company.com")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "https://" + u
    p = urlsplit(u)
    host = (p.hostname or "").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if (ip is not None and not ip.is_global) or host == "localhost" or host.endswith((".local", ".localhost", ".internal", ".lan", ".home")):
        raise ValueError("Private or local addresses are not allowed")
    if p.scheme not in ("http", "https") or not host or "." not in host or p.username or p.password:
        raise ValueError("Enter a public website address such as https://company.com")
    return f"{p.scheme}://{host}"


def _host(origin: str) -> str:
    return (urlsplit(origin).hostname or "").removeprefix("www.")


def default_name(origin: str) -> str:
    return _host(origin).split(".")[0].replace("-", " ").replace("_", " ").title()


def suggest_offer(category: str, text: str) -> str:
    cat = CATEGORIES.get(category, CATEGORIES["company"])
    if category in ("agency", "network"):
        return cat["offer"]
    best, best_n = cat["offer"], 0
    for key, o in OFFERS.items():
        if key in ("subcontract_capacity", "network_application"):
            continue
        n = len(re.findall(o["keywords"], text or "", re.I))
        if n > best_n:
            best, best_n = key, n
    return best


def prospect_signals(text: str, has_careers_page: bool, has_mailbox: bool) -> tuple[float, list[str]]:
    """0-100 and the list of reasons. These are public signs a company MAY need this work; they are not proof."""
    pts, notes = 0, []
    for pat, p, label in _SIGNALS:
        if re.search(pat, text or "", re.I):
            pts += p
            notes.append(f"{label} (+{p})")
    if has_careers_page:
        pts += 15
        notes.append("Has a careers/jobs page: they hire technical people (+15)")
    if leads.invites_freelancers(text or ""):
        pts += 25
        notes.append("Its site invites freelancers or contractors to get in touch (+25)")
    if has_mailbox:
        pts += 10
        notes.append("Publishes a role mailbox (+10)")
    return float(min(100, pts)), notes


def _variants(origin: str) -> list[str]:
    host = _host(origin)
    return [f"{scheme}://{www}{host}" for scheme in ("https", "http") for www in ("", "www.")]


def get_or_create_company(db: Session, origin: str, name: str) -> Company:
    """The company that owns this website. A company is matched by its website (with or without www); one known only
    by name is adopted only if it has no website yet, otherwise research would read the wrong site."""
    c = db.scalar(select(Company).where(Company.website.in_(_variants(origin))))
    if c:
        return c
    if name:
        c = db.scalar(select(Company).where(Company.name_norm == norm_text(name),
                                            or_(Company.website == "", Company.website.is_(None))))
        if c:
            c.website, c.website_source = origin, "user"
            return c
    label = (name or default_name(origin))[:300]
    c = Company(name=label, name_norm=norm_text(label), website=origin, website_source="user")
    db.add(c)
    db.flush()
    return c


def add_prospect(db: Session, website: str, name: str = "", category: str = "company", offer: str = "",
                 evidence_url: str = "", evidence_quote: str = "") -> Opportunity:
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    if offer and offer not in OFFERS:
        raise ValueError("Unknown offer")
    if evidence_url and not re.match(r"^https?://", evidence_url, re.I):
        raise ValueError("The evidence link must be an http(s) address")
    origin = normalize_site(website)
    ext = "prospect:" + _host(origin)
    meta = {"category": category, "offer": offer or CATEGORIES[category]["offer"], "offer_auto": not offer,
            "evidence_url": evidence_url.strip(), "evidence_quote": evidence_quote.strip()[:600]}
    opp = db.scalar(select(Opportunity).where(Opportunity.source_key == SOURCE, Opportunity.external_id == ext))
    if opp:     # the same site again (with or without www): update, never a second record
        opp.meta = {**(opp.meta or {}), **{k: v for k, v in meta.items() if v not in ("", None)}}
        if name.strip():
            opp.title = opp.company_name = name.strip()[:300]
        db.commit()
        return opp
    company = get_or_create_company(db, origin, name.strip())
    opp = Opportunity(
        source_key=SOURCE, source_type="manual", external_id=ext, original_url=origin, canonical_url=origin,
        fingerprint=hashlib.sha256(ext.encode()).hexdigest(), title=(name.strip() or company.name)[:500],
        company_id=company.id, company_name=company.name, description=meta["evidence_quote"], engagement_type="unknown",
        remote_status="unknown", research_status="not_started", review_status="new", meta=meta,
        recommended_action="Research the site, then approve a fact and draft a pitch")
    db.add(opp)
    db.commit()
    return opp


def _usable(stmt):
    return stmt.where(BusinessContact.source_url != "", BusinessContact.suppressed.is_(False),
                      BusinessContact.outreach_eligibility != "not_eligible")


def research_prospect(db: Session, opp: Opportunity, fetcher: SafeFetcher | None = None) -> dict:
    """Read the company's own site, keep evidence, find role mailboxes, compute the signals. Never contacts anyone."""
    fetcher = fetcher or SafeFetcher()
    company = db.get(Company, opp.company_id)
    category = (opp.meta or {}).get("category", "company")
    mode = "application" if category == "network" else "pitch"
    opp.research_status = "researching"
    db.commit()
    report: dict = {}
    try:
        research.research_company(db, company, opp, fetcher, mode=mode, report=report)
    except Exception as e:  # noqa: BLE001
        company.research_status, company.last_error = "failed", str(e)[:300]
        db.commit()
    pages = report.get("pages", [])
    text = report.get("text", "")
    home = pages[0] if pages else ""
    has_careers = any(re.search(r"/(careers|jobs|join-us|work-with-us)/?$", u) for u in pages if u.rstrip("/") != home.rstrip("/"))
    contacts = db.scalars(_usable(select(BusinessContact).where(BusinessContact.opportunity_id == opp.id))).all()
    pts, notes = prospect_signals(text, has_careers, bool(contacts))
    if category == "network":      # a network does not "need" work done; the score would only mislead
        pts, notes = 0.0, []
    facts = db.scalars(select(Evidence).where(Evidence.company_id == company.id, Evidence.kind == "fact")).all()
    sc = score(RawOpportunity(source_key=SOURCE, url=opp.original_url, title=opp.title, company_name=company.name,
                              description=text or company.description or "", remote_status="remote"), None)
    meta = dict(opp.meta or {})
    if meta.get("offer_auto", True):
        meta["offer"] = suggest_offer(category, text)
    meta["pages"], meta["researched_at"] = pages, utcnow().isoformat()
    opp.meta = meta
    opp.research_status = company.research_status
    opp.ease_score, opp.ease_signals = pts, notes
    opp.fit_score = round(sc["components"]["skills"] / 35 * 100, 1)
    opp.required_skills, opp.matched_skills = sc["detected_skills"], sc["matched_skills"]
    opp.apply_method = "email" if contacts else "link"
    desc = [company.description] if company.description else []
    desc += [f.excerpt for f in facts if f.excerpt and f.excerpt != company.description][:6]
    if meta.get("evidence_quote"):
        desc.append(f"(Why added: {meta['evidence_quote']})")
    opp.description = "\n".join(desc)[:4000]
    opp.last_verified_at = utcnow()
    if company.research_status == "failed":
        opp.recommended_action = f"Could not read the website ({company.last_error[:80]}). Check the address."
    elif contacts:
        opp.recommended_action = "Review the evidence, approve one fact, then draft a pitch to the published mailbox"
    else:
        opp.recommended_action = "No mailbox found on the site: use its contact form (read the evidence first)"
    db.commit()
    return {"pages": len(pages), "mailboxes": len(contacts), "signals": len(notes), "status": company.research_status}


def research_many(session_factory, ids: list[int], fetcher_factory=SafeFetcher) -> None:
    """Background task: one prospect after the other, each with its own commit; failures are recorded, never raised."""
    for pid in ids:
        with session_factory() as db:
            opp = db.get(Opportunity, pid)
            if not opp or opp.source_key != SOURCE:
                continue
            try:
                research_prospect(db, opp, fetcher_factory())
            except Exception as e:  # noqa: BLE001
                db.rollback()
                opp = db.get(Opportunity, pid)
                opp.research_status = "failed"
                opp.recommended_action = f"Research failed: {type(e).__name__}"
                db.commit()


def reset_stuck(db: Session) -> int:
    """After a restart, prospects left 'researching' go back to 'not_started' so they can be researched again."""
    n = 0
    for o in db.scalars(select(Opportunity).where(Opportunity.source_key == SOURCE, Opportunity.research_status == "researching")):
        o.research_status = "not_started"
        n += 1
    db.commit()
    return n


def delete_prospect(db: Session, opp: Opportunity) -> None:
    if db.scalar(select(Application.id).where(Application.opportunity_id == opp.id)):
        raise ValueError("An application is recorded for this prospect; it cannot be removed")
    db.execute(delete(BusinessContact).where(BusinessContact.opportunity_id == opp.id,
                                             BusinessContact.source_type == "company_website"))
    db.execute(delete(ProposalDraft).where(ProposalDraft.opportunity_id == opp.id))
    db.execute(delete(OpportunityHistory).where(OpportunityHistory.opportunity_id == opp.id))
    db.execute(update(Evidence).where(Evidence.opportunity_id == opp.id).values(opportunity_id=None))   # company facts stay
    db.delete(opp)
    db.commit()
