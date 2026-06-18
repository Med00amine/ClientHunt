from datetime import timedelta

from app.adapters.base import Adapter, AdapterError, AdapterUnavailable
from app.models import utcnow
from app.types import RawOpportunity


def raw(i=1, title=None, **kw):
    d = dict(source_key="fake", external_id=str(i), url=f"https://example.com/jobs/{i}",
             title=title or f"Python FastAPI engineer for LLM RAG on AWS #{i}",
             company_name=f"Acme {i}", description=("We need Python, FastAPI, Docker, AWS and LLM/RAG work. " * 12),
             posted_at=utcnow() - timedelta(days=1), remote_status="remote", location_requirements="Worldwide",
             engagement_type="contract")
    d.update(kw)
    return RawOpportunity(**d)


class FakeAdapter(Adapter):
    key = "fake"

    def __init__(self, items=None, error=None, unavailable=None):
        self.items, self.error, self.unavail = items or [], error, unavailable

    def fetch(self, params):
        if self.unavail:
            raise AdapterUnavailable(self.unavail)
        if self.error:
            raise AdapterError(self.error)
        return list(self.items)


def factory_for(mapping):
    def f(key, db):
        return mapping[key]
    return f
