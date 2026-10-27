"""Gemini letter drafting (§10.2): the LLM fills a template with pre-
computed slots (amount, cause, issues) and may not change the amount or
add commitments — the Gate (Task 8) re-checks both."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, Remedy


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


def draft_letter(session_factory: sessionmaker, remedy_id: str, provider: LetterProvider) -> dict:
    with session_factory() as session:
        remedy = session.get(Remedy, remedy_id)
        complaint = session.get(Complaint, remedy.complaint_id)
        run_id = session.get(Cohort, remedy.cohort_id).run_id
        features = session.get(ComplaintFeatures, {"run_id": run_id, "complaint_id": remedy.complaint_id})
        extraction = features.extraction if features else {}

        draft_text = provider.draft(amount=str(remedy.amount), claimed_cause=extraction.get("claimed_cause", "the reported issue"), issues=extraction.get("issues", []))

        session.query(Letter).filter(Letter.remedy_id == remedy_id).delete()  # idempotent re-run
        session.add(Letter(id=f"letter-{remedy_id}", remedy_id=remedy_id, complaint_id=complaint.complaint_id, draft=draft_text, prompt_version=provider.prompt_version, gate_result=None))
        session.commit()
    return {"drafted": True, "remedy_id": remedy_id}
