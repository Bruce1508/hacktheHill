"""Consistency Gate orchestration (§10.3): rules first (free), then the one
LLM check ("every issue addressed"), only if every rule already passed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, Remedy
from backtrace.gate.rules import check_amount, check_forbidden_phrases, check_vulnerability

FORBIDDEN_PHRASES = ("guarantee", "lifetime", "unlimited")


class GateLlmProvider(Protocol):
    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool: ...


@dataclass
class FakeGateLlmProvider:
    fake_all_issues_addressed: bool = True
    fail_if_called: bool = False

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
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool:
        from backtrace.llm.prompts import GATE_ISSUES_PROMPT_V1

        prompt = GATE_ISSUES_PROMPT_V1.format(letter_text=letter_text, issues=", ".join(issues))
        resp = self._client.models.generate_content(model=self.model_id, contents=prompt)
        return resp.text.strip().lower().startswith("yes")


def run_gate(session_factory: sessionmaker, letter_id: str, provider: GateLlmProvider) -> dict:
    with session_factory() as session:
        letter = session.get(Letter, letter_id)
        remedy = session.get(Remedy, letter.remedy_id)
        cohort = session.get(Cohort, remedy.cohort_id)
        features = session.get(ComplaintFeatures, {"run_id": cohort.run_id, "complaint_id": letter.complaint_id})
        extraction = features.extraction if features else {}

        rule_results = [
            check_amount(letter.draft, remedy.amount),
            check_forbidden_phrases(letter.draft, FORBIDDEN_PHRASES),
            check_vulnerability(extraction.get("vulnerability_signals", [])),
        ]
        failed = next((r for r in rule_results if not r.passed), None)
        if failed is not None:
            gate_result = {"status": "fail", "reason": f"{failed.check}: {failed.reason}"}
        else:
            addressed = provider.all_issues_addressed(letter.draft, extraction.get("issues", []))
            gate_result = {"status": "pass"} if addressed else {"status": "needs_review", "reason": "not every issue addressed"}

        letter.gate_result = gate_result
        session.commit()
    return gate_result
