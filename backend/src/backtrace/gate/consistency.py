"""Consistency Gate orchestration (§10.3): rules first (free), then the one
LLM check ("every issue addressed"), only if every rule already passed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, Remedy
from backtrace.gate.rules import check_amount, check_forbidden_phrases, check_vulnerability
from backtrace.llm.cache import cache_key, get_cached, put_cached
from backtrace.llm.providers import NO_RETRY, REQUEST_TIMEOUT_MS
from backtrace.llm.rate_limit import RateLimiter


class GateLlmProvider(Protocol):
    model_id: str
    prompt_version: str

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool: ...


@dataclass
class FakeGateLlmProvider:
    fake_all_issues_addressed: bool = True
    fail_if_called: bool = False
    prompt_version: str = "gate-v1"

    @property
    def model_id(self) -> str:
        # The fake's answer is part of its identity, so a "yes" fake and a
        # "no" fake never share an llm_cache entry for the same letter.
        return f"fake-gate-{'yes' if self.fake_all_issues_addressed else 'no'}-v1"

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool:
        if self.fail_if_called:
            raise AssertionError("LLM check must not run when a rule already failed")
        return self.fake_all_issues_addressed


class GeminiGateLlmProvider:
    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        import os

        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool:
        from backtrace.llm.prompts import GATE_ISSUES_PROMPT_V1

        prompt = GATE_ISSUES_PROMPT_V1.format(letter_text=letter_text, issues=", ".join(issues))
        resp = self._client.models.generate_content(model=self.model_id, contents=prompt)
        return resp.text.strip().lower().startswith("yes")


def run_gate(session_factory: sessionmaker, letter_id: str, provider: GateLlmProvider, forbidden_phrases: tuple[str, ...], rate_limiter: RateLimiter | None = None) -> dict:
    with session_factory() as session:
        letter = session.get(Letter, letter_id)
        remedy = session.get(Remedy, letter.remedy_id)
        cohort = session.get(Cohort, remedy.cohort_id)
        features = session.get(ComplaintFeatures, {"run_id": cohort.run_id, "complaint_id": letter.complaint_id})
        extraction = features.extraction if features else {}

        rule_results = [
            check_amount(letter.draft, remedy.amount),
            check_forbidden_phrases(letter.draft, forbidden_phrases),
            check_vulnerability(extraction.get("vulnerability_signals", [])),
        ]
        failed = next((r for r in rule_results if not r.passed), None)
        if failed is not None:
            gate_result = {"status": "fail", "reason": f"{failed.check}: {failed.reason}"}
        else:
            # llm_cache-backed like extract_complaint (§8.5): re-gating an
            # unchanged letter costs zero tokens.
            issues = extraction.get("issues", [])
            key = cache_key(provider.model_id, provider.prompt_version, letter.draft, issues=issues)
            cached = get_cached(session, key)
            if cached is not None:
                addressed = cached["all_issues_addressed"]
            else:
                letter_text = letter.draft
                session.commit()  # release the connection before the slow network call
                if rate_limiter is not None:
                    rate_limiter.acquire()
                addressed = provider.all_issues_addressed(letter_text, issues)
                put_cached(session, key, {"all_issues_addressed": addressed})
            gate_result = {"status": "pass"} if addressed else {"status": "needs_review", "reason": "not every issue addressed"}

        letter.gate_result = gate_result
        session.commit()
    return gate_result
