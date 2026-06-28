from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawOpportunity:
    source_key: str
    url: str
    title: str
    external_id: str = ""
    company_name: str = ""
    company_website: str = ""
    company_website_source: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    deadline: datetime | None = None
    engagement_type: str = "unknown"   # contract|freelance|part_time|full_time|unknown
    remote_status: str = "unknown"     # remote|hybrid|onsite|unknown
    location_requirements: str = ""
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = ""
    rate_type: str = ""
    source_type: str = "api"


@dataclass
class SearchParams:
    keywords: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    remote_only: bool = True
    engagement_types: list[str] = field(default_factory=list)
    min_rate: float | None = None
    max_rate: float | None = None
    country: str = ""
    experience_level: str = ""
    languages: list[str] = field(default_factory=list)
    posted_within_days: int | None = 30
    max_results: int = 100
    max_budget_usd: float = 1.0
    min_fit: float = 20.0
    min_ease: float = 0.0
    require_email: bool = False
    strict_engagement: bool = False   # drop listings whose engagement type is unknown
    max_companies: int | None = None
    max_drafts: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SearchParams":
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)
