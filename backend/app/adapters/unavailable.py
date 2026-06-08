"""Sources that need authorisation (or have no permitted API) report that honestly."""
from ..config import get_settings
from ..types import RawOpportunity, SearchParams
from .base import Adapter, AdapterUnavailable, register


@register
class Upwork(Adapter):
    key, name = "upwork", "Upwork (official API)"

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        raise AdapterUnavailable(
            "Upwork API access requires approval (earnings/JSS thresholds, non-commercial use) and no verified "
            "job-search endpoint was confirmed. Use Upwork saved-search email alerts via 'Alert import'.")


@register
class Freelancer(Adapter):
    key, name = "freelancer", "Freelancer.com (official API)"

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        if not get_settings().freelancer_oauth_token:
            raise AdapterUnavailable("No FREELANCER_OAUTH_TOKEN configured. The API endpoints/terms were not "
                                     "verified from official docs; adapter intentionally not implemented.")
        raise AdapterUnavailable("Freelancer.com adapter not implemented: official docs could not be verified.")
