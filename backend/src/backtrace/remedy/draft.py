"""Gemini letter drafting (§10.2): the LLM fills a template with pre-
computed slots (amount, cause, issues) and may not change the amount or
add commitments — the Gate (Task 8) re-checks both."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, Remedy
from backtrace.llm.cache import cache_key, get_cached, put_cached
from backtrace.llm.rate_limit import RateLimiter


class LetterProvider(Protocol):
    model_id: str
    prompt_version: str

    def draft(self, amount: str, claimed_cause: str, issues: list[str]) -> str: ...


@dataclass
class FakeLetterProvider:
    model_id: str = "fake-letter-v1"
    prompt_version: str = "letter-v1"

    def draft(self, amount: str, claimed_cause: str, issues: list[str]) -> str:
        return f"Dear customer, regarding {claimed_cause} ({', '.join(issues)}), we are issuing a credit of ${amount}."


def draft_letter(session_factory: sessionmaker, remedy_id: str, provider: LetterProvider, rate_limiter: RateLimiter | None = None) -> dict:
    """llm_cache-backed like extract_complaint (§8.5): redrafting the same
    remedy with the same model/prompt_version costs zero tokens."""
    with session_factory() as session:
        remedy = session.get(Remedy, remedy_id)
        complaint = session.get(Complaint, remedy.complaint_id)
        run_id = session.get(Cohort, remedy.cohort_id).run_id
        features = session.get(ComplaintFeatures, {"run_id": run_id, "complaint_id": remedy.complaint_id})
        extraction = features.extraction if features else {}

        amount = str(remedy.amount)
        claimed_cause = extraction.get("claimed_cause", "the reported issue")
        issues = extraction.get("issues", [])
        key = cache_key(provider.model_id, provider.prompt_version, claimed_cause, amount=amount, issues=issues)
        cached = get_cached(session, key)
        if cached is not None:
            draft_text = cached["draft"]
        else:
            session.commit()  # release the connection before the slow network call
            if rate_limiter is not None:
                rate_limiter.acquire()
            draft_text = provider.draft(amount=amount, claimed_cause=claimed_cause, issues=issues)
            put_cached(session, key, {"draft": draft_text})

        session.query(Letter).filter(Letter.remedy_id == remedy_id).delete()  # idempotent re-run
        session.add(Letter(id=f"letter-{remedy_id}", remedy_id=remedy_id, complaint_id=complaint.complaint_id, draft=draft_text, prompt_version=provider.prompt_version, gate_result=None))
        session.commit()
    return {"drafted": True, "remedy_id": remedy_id}
