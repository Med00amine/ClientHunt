from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    password: str


class SearchIn(BaseModel):
    name: str = Field(default="Ad-hoc search", max_length=120)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    required_skills: list[str] = Field(default_factory=list, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=20)
    remote_only: bool = True
    engagement_types: list[str] = Field(default_factory=list)
    min_rate: float | None = Field(default=None, ge=0)
    max_rate: float | None = Field(default=None, ge=0)
    country: str = Field(default="", max_length=80)
    experience_level: str = Field(default="", max_length=40)
    languages: list[str] = Field(default_factory=list)
    posted_within_days: int | None = Field(default=30, ge=1, le=365)
    max_results: int = Field(default=100, ge=1, le=500)
    max_budget_usd: float = Field(default=1.0, ge=0, le=100)
    min_fit: float = Field(default=20.0, ge=0, le=100)
    min_ease: float = Field(default=0.0, ge=0, le=100)
    require_email: bool = False
    max_companies: int | None = Field(default=None, ge=0, le=100)
    max_drafts: int | None = Field(default=None, ge=0, le=100)


class RunIn(BaseModel):
    profile_id: int | None = None
    search: SearchIn | None = None


class ProfileIn(BaseModel):
    name: str = Field(max_length=120)
    params: SearchIn


class OppPatch(BaseModel):
    review_status: str | None = Field(default=None, pattern="^(new|shortlisted|excluded)$")
    exclusion_reason: str | None = Field(default=None, max_length=300)
    score_override: float | None = Field(default=None, ge=0, le=100)
    clear_score_override: bool = False
    company_website: str | None = Field(default=None, max_length=500)


class ManualIn(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    url: str = Field(min_length=8, max_length=1000, pattern="^https?://")
    company_name: str = Field(default="", max_length=300)
    company_website: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=20000)
    engagement_type: str = Field(default="unknown", pattern="^(contract|freelance|part_time|full_time|unknown)$")
    location_requirements: str = Field(default="", max_length=500)
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = Field(default="", max_length=10)
    rate_type: str = Field(default="", pattern="^(hourly|fixed|annual|monthly|)$")


class AlertIn(BaseModel):
    text: str = Field(min_length=10, max_length=500000)
    platform_hint: str = Field(default="", max_length=30)


class DraftPatch(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ApproveIn(BaseModel):
    acknowledge_warnings: bool = False


class ApplicationIn(BaseModel):
    draft_id: int | None = None
    notes: str = Field(default="", max_length=2000)


class ApplicationPatch(BaseModel):
    status: str = Field(pattern="^(submitted|replied|interview|won|lost|withdrawn)$")
    notes: str | None = Field(default=None, max_length=2000)


class ConversationIn(BaseModel):
    direction: str = Field(default="in", pattern="^(in|out)$")
    summary: str = Field(max_length=2000)


class EligibilityIn(BaseModel):
    value: str
    basis: str = ""


class SuppressIn(BaseModel):
    email: str = ""
    domain: str = ""
    reason: str = ""


class ContactIn(BaseModel):
    email: str = Field(max_length=320)
    name: str = Field(default="", max_length=300)
    role: str = Field(default="", max_length=200)
    company_name: str = Field(default="", max_length=300)
    source_url: str = Field(min_length=8, max_length=1000, pattern="^https?://")
    source_note: str = Field(default="", max_length=500)


class EvidenceApprove(BaseModel):
    approved: bool


class PortfolioToggle(BaseModel):
    verified: bool
    url: str | None = None
