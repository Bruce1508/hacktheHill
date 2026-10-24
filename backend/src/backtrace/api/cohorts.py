import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from backtrace.api.auth import CurrentUser, current_user
from backtrace.contracts.evidence import CohortEvidenceOut, CohortListOut, CohortOut
from backtrace.db.models import Cohort, CohortMember
from backtrace.db.session import get_session
from backtrace.pipeline.hypothesis import build_evidence_pack

router = APIRouter()


def _cohort_out(session, cohort: Cohort) -> CohortOut:
    member_count = session.execute(select(func.count()).where(CohortMember.cohort_id == cohort.id)).scalar_one()
    return CohortOut(id=cohort.id, run_id=cohort.run_id, status=cohort.status, kind=cohort.kind, hypothesis=cohort.hypothesis, confidence=cohort.confidence, member_count=member_count)


@router.get("/cohorts")
def list_cohorts(_user: Annotated[CurrentUser, Depends(current_user)], run_id: Annotated[str, Query()]) -> CohortListOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohorts = session.execute(select(Cohort).where(Cohort.run_id == run_id)).scalars().all()
        return CohortListOut(cohorts=[_cohort_out(session, c) for c in cohorts])


@router.get("/cohorts/{cohort_id}")
def get_cohort(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        return _cohort_out(session, cohort)


@router.get("/cohorts/{cohort_id}/evidence")
def get_cohort_evidence(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortEvidenceOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        pack = build_evidence_pack(session, cohort_id)
        return CohortEvidenceOut(
            cohort_id=cohort_id, score_components=pack.score_components, hypothesis=cohort.hypothesis,
            hypothesis_citations=cohort.hypothesis_citations, linked_event_ids=pack.event_ids,
            linked_anomaly_ids=pack.anomaly_ids, sample_complaint_ids=pack.complaint_ids[:5],
        )
