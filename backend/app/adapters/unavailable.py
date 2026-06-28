"""Sources that need authorisation (or have no permitted API) report that honestly."""
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
    key, name = "freelancer", "Freelancer.com (stored in runs)"

    def fetch(self, params: SearchParams) -> list[RawOpportunity]:
        raise AdapterUnavailable(
            "Freelancer.com's API terms say 'You may not copy or store any Data', so its projects are not stored in "
            "runs or exports. Use the Live projects tab (shown live, never saved) and bid on Freelancer.com yourself.")
