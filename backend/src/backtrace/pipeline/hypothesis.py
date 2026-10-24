"""Gemini hypothesis generation over a real evidence pack (§8.2 step 8).
A hypothesis that cites an id not present in its own pack is rejected
outright — citations are the only thing standing between a plausible-
sounding guess and a claim a reviewer can actually check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backtrace.contracts.evidence import EvidencePack, HypothesisOutput
from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint

SAMPLE_COMPLAINT_CAP = 5


class HypothesisProvider(Protocol):
    model_id: str
    prompt_version: str

    def generate(self, pack: EvidencePack) -> HypothesisOutput: ...


@dataclass
class FakeHypothesisProvider:
    """Deterministic test double — set fake_cited_* to test the citation
    validator without a real Gemini call."""

    model_id: str = "fake-hypothesis-v1"
    prompt_version: str = "hypothesis-v1"
    fake_cited_complaint_ids: list[str] | None = None
    fake_cited_event_ids: list[str] | None = None
    fake_cited_anomaly_ids: list[str] | None = None

    def generate(self, pack: EvidencePack) -> HypothesisOutput:
        return HypothesisOutput(
            text="Fake hypothesis for testing.",
            cited_complaint_ids=self.fake_cited_complaint_ids or [],
            cited_event_ids=self.fake_cited_event_ids or [],
            cited_anomaly_ids=self.fake_cited_anomaly_ids or [],
        )


def build_evidence_pack(session: Session, cohort_id: str) -> EvidencePack:
    complaint_ids = [
        row[0] for row in session.execute(
            select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id)
        )
    ]
    links = session.execute(select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id)).scalars().all()
    event_ids = sorted({link.event_id for link in links if link.event_id})
    anomaly_ids = sorted({link.anomaly_id for link in links if link.anomaly_id})

    totals: dict[str, float] = {}
    for link in links:
        for key, value in link.evidence.items():
            totals[key] = totals.get(key, 0.0) + value
    score_components = {k: v / len(links) for k, v in totals.items()} if links else {}

    sample_texts = [
        row[0] for row in session.execute(
            select(Complaint.text).where(Complaint.complaint_id.in_(complaint_ids)).limit(SAMPLE_COMPLAINT_CAP)
        )
    ]
    return EvidencePack(
        cohort_id=cohort_id, complaint_ids=sorted(complaint_ids), event_ids=event_ids, anomaly_ids=anomaly_ids,
        score_components=score_components, sample_complaint_texts=sample_texts,
    )


def _validate_citations(pack: EvidencePack, output: HypothesisOutput) -> bool:
    return (
        set(output.cited_complaint_ids) <= set(pack.complaint_ids)
        and set(output.cited_event_ids) <= set(pack.event_ids)
        and set(output.cited_anomaly_ids) <= set(pack.anomaly_ids)
    )


def run_hypothesis_stage(session_factory: sessionmaker, run_id: str, provider: HypothesisProvider) -> dict:
    with session_factory() as session:
        cohort_ids = [row[0] for row in session.execute(select(Cohort.id).where(Cohort.run_id == run_id))]

    accepted = rejected = 0
    for cohort_id in cohort_ids:
        with session_factory() as session:
            pack = build_evidence_pack(session, cohort_id)
            if not pack.complaint_ids:
                continue
            output = provider.generate(pack)
            if not _validate_citations(pack, output):
                rejected += 1
                continue
            accepted += 1
            cohort = session.get(Cohort, cohort_id)
            cohort.hypothesis = output.text
            cohort.hypothesis_citations = {
                "complaint_ids": output.cited_complaint_ids,
                "event_ids": output.cited_event_ids,
                "anomaly_ids": output.cited_anomaly_ids,
            }
            cohort.confidence = len(output.cited_complaint_ids + output.cited_event_ids + output.cited_anomaly_ids) / max(
                1, len(pack.complaint_ids) + len(pack.event_ids) + len(pack.anomaly_ids)
            )
            session.commit()
    return {"accepted": accepted, "rejected": rejected}
