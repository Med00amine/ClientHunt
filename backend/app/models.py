"""Database schema. Opportunities and business contacts are deliberately separate entities."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored naive UTC


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # api | alert | manual | unavailable
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    terms_url: Mapped[str] = mapped_column(String(500), default="")
    docs_url: Mapped[str] = mapped_column(String(500), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # docs/terms verified on checked_at
    checked_at: Mapped[str] = mapped_column(String(20), default="")


class SearchProfile(Base):
    __tablename__ = "search_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_norm: Mapped[str] = mapped_column(String(300), index=True)
    website: Mapped[str] = mapped_column(String(500), default="")
    website_source: Mapped[str] = mapped_column(String(30), default="")  # listing_field|listing_text|user
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(200), default="")
    research_status: Mapped[str] = mapped_column(String(30), default="not_started")
    researched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ResearchRun(Base):
    """A research run is also the persistent job record."""
    __tablename__ = "research_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("search_profiles.id"), nullable=True)
    profile_name: Mapped[str] = mapped_column(String(120), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending | running | completed | partial | failed | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_source: Mapped[str] = mapped_column(String(60), default="")
    sources_queried: Mapped[list] = mapped_column(JSON, default=list)
    source_results: Mapped[dict] = mapped_column(JSON, default=dict)  # key -> {status, fetched, error}
    discovered: Mapped[int] = mapped_column(Integer, default=0)       # raw items fetched
    stored: Mapped[int] = mapped_column(Integer, default=0)           # relevant, stored/seen in this run
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_irrelevant: Mapped[int] = mapped_column(Integer, default=0)
    rejected_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    selected_for_review: Mapped[int] = mapped_column(Integer, default=0)
    companies_researched: Mapped[int] = mapped_column(Integer, default=0)
    drafts_generated: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str] = mapped_column(Text, default="")
    errors: Mapped[list] = mapped_column(JSON, default=list)
    incomplete_notes: Mapped[list] = mapped_column(JSON, default=list)
    info_notes: Mapped[list] = mapped_column(JSON, default=list)  # configured caps etc.; not a failure
    export_status: Mapped[str] = mapped_column(String(20), default="none")  # none|ok|failed
    exports: Mapped[list["ExportRecord"]] = relationship(back_populates="run")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("source_key", "external_id", name="uq_opp_source_ext"),
                      Index("ix_opp_fingerprint", "fingerprint"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="api")  # api | alert | manual
    external_id: Mapped[str] = mapped_column(String(300))  # source id, or url-hash when no id
    original_url: Mapped[str] = mapped_column(String(1000))
    canonical_url: Mapped[str] = mapped_column(String(1000), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(500))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    company_name: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engagement_type: Mapped[str] = mapped_column(String(20), default="unknown")
    remote_status: Mapped[str] = mapped_column(String(20), default="unknown")
    location_requirements: Mapped[str] = mapped_column(String(500), default="")
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="")
    rate_type: Mapped[str] = mapped_column(String(20), default="")  # hourly|fixed|annual|monthly|""
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listing_status: Mapped[str] = mapped_column(String(20), default="open")  # open|closed|unknown
    # scoring
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_components: Mapped[dict] = mapped_column(JSON, default=dict)
    fit_explanation: Mapped[str] = mapped_column(Text, default="")
    portfolio_evidence: Mapped[list] = mapped_column(JSON, default=list)
    score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[str] = mapped_column(String(300), default="")
    # workflow
    review_status: Mapped[str] = mapped_column(String(20), default="new")  # new|shortlisted|excluded
    exclusion_reason: Mapped[str] = mapped_column(String(300), default="")
    research_status: Mapped[str] = mapped_column(String(30), default="not_started")
    proposal_status: Mapped[str] = mapped_column(String(20), default="none")
    application_status: Mapped[str] = mapped_column(String(20), default="none")
    # "easy to reach" heuristic (not a hiring prediction) and how to apply
    ease_score: Mapped[float] = mapped_column(Float, default=0.0)
    ease_signals: Mapped[list] = mapped_column(JSON, default=list)
    apply_method: Mapped[str] = mapped_column(String(10), default="unknown")  # email | link | unknown
    # free-form extras; for prospects: category, offer, evidence_url, evidence_quote, pages, origin
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    company: Mapped[Company | None] = relationship()


class OpportunityHistory(Base):
    __tablename__ = "opportunity_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    change: Mapped[dict] = mapped_column(JSON, default=dict)


class RunOpportunity(Base):
    """Which opportunities a run saw (basis of the per-run CSV)."""
    __tablename__ = "run_opportunities"
    __table_args__ = (UniqueConstraint("run_id", "opportunity_id", name="uq_run_opp"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("research_runs.id"), index=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Evidence(Base):
    __tablename__ = "research_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # fact | hypothesis
    claim: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class BusinessContact(Base):
    __tablename__ = "business_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    email_norm: Mapped[str] = mapped_column(String(320), unique=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    role: Mapped[str] = mapped_column(String(200), default="")
    company_name: Mapped[str] = mapped_column(String(300), default="")
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    is_generic: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(30), default="imported_file")
    source_url: Mapped[str] = mapped_column(String(1000), default="")  # blank = provenance missing
    source_note: Mapped[str] = mapped_column(String(500), default="")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_status: Mapped[str] = mapped_column(String(20), default="unverified")
    outreach_eligibility: Mapped[str] = mapped_column(String(20), default="unknown")
    eligibility_basis: Mapped[str] = mapped_column(String(500), default="")
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    contact_purpose: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Suppression(Base):
    __tablename__ = "suppressions"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_norm: Mapped[str] = mapped_column(String(320), default="", index=True)
    domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProposalDraft(Base):
    __tablename__ = "proposal_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|rejected
    generator: Mapped[str] = mapped_column(String(20), default="template")  # template|llm
    rationale: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    portfolio_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Application(Base):
    """Created only when the user records that they submitted a proposal on the platform."""
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"), unique=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("proposal_drafts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    # submitted|replied|interview|won|lost|withdrawn
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")


class Conversation(Base):
    __tablename__ = "client_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="in")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    summary: Mapped[str] = mapped_column(Text, default="")


class ExportRecord(Base):
    __tablename__ = "export_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="opportunities")
    filename: Mapped[str] = mapped_column(String(300), default="")
    path: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok | failed
    error: Mapped[str] = mapped_column(Text, default="")
    run_status: Mapped[str] = mapped_column(String(20), default="")
    run: Mapped[ResearchRun | None] = relationship(back_populates="exports")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(20))  # llm | search | api
    provider: Mapped[str] = mapped_column(String(60), default="")
    units: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(300), default="")


class HttpCache(Base):
    __tablename__ = "http_cache"
    key: Mapped[str] = mapped_column(String(500), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    body: Mapped[str] = mapped_column(Text, default="")
