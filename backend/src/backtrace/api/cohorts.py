import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from backtrace.api.auth import CurrentUser, current_user
from backtrace.audit import append_audit
from backtrace.contracts.evidence import AnomalyWindowOut, CohortEvidenceOut, CohortListOut, CohortOut, CohortTimelineOut, ComplaintBucketOut
from backtrace.contracts.remedy import RemedyComputeOut
from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, DetectedAnomaly
from backtrace.db.session import get_session, make_session_factory
from backtrace.pipeline.hypothesis import build_evidence_pack
from backtrace.remedy.engine import compute_cohort_remedies

router = APIRouter()

REVIEW_ROLES = {"team_lead", "compliance"}
TIMELINE_BUCKET_MINUTES = 15


def _require_review_role(user: CurrentUser) -> None:
    if user.role not in REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="requires team_lead or compliance")


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


@router.get("/cohorts/{cohort_id}/timeline")
def get_cohort_timeline(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortTimelineOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")

        complaint_ids = [row[0] for row in session.execute(select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id))]
        received_ats = [
            row[0] for row in session.execute(select(Complaint.received_at).where(Complaint.complaint_id.in_(complaint_ids)))
        ]
        buckets: dict = {}
        for received_at in received_ats:
            bucket_start = received_at.replace(minute=(received_at.minute // TIMELINE_BUCKET_MINUTES) * TIMELINE_BUCKET_MINUTES, second=0, microsecond=0)
            buckets[bucket_start] = buckets.get(bucket_start, 0) + 1
        complaint_buckets = [ComplaintBucketOut(bucket_start=k.isoformat(), count=v) for k, v in sorted(buckets.items())]

        links = session.execute(select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id, CohortEventLink.anomaly_id.isnot(None))).scalars().all()
        anomaly_windows = []
        for link in links:
            anomaly = session.get(DetectedAnomaly, link.anomaly_id)
            anomaly_windows.append(AnomalyWindowOut(anomaly_id=anomaly.id, metric=anomaly.metric, start_at=anomaly.start_at.isoformat(), end_at=anomaly.end_at.isoformat(), peak_score=anomaly.peak_score))

        return CohortTimelineOut(cohort_id=cohort_id, complaint_buckets=complaint_buckets, anomaly_windows=anomaly_windows)


@router.post("/cohorts/{cohort_id}/confirm")
def confirm_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "confirmed"
        append_audit(session, user.user_id, user.role, "dev", "cohort.confirm", "cohort", cohort_id, before=before, after={"status": "confirmed"})
        session.commit()
        return _cohort_out(session, cohort)


@router.post("/cohorts/{cohort_id}/split")
def split_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "split"
        append_audit(session, user.user_id, user.role, "dev", "cohort.split", "cohort", cohort_id, before=before, after={"status": "split"})
        session.commit()
        return _cohort_out(session, cohort)


@router.post("/cohorts/{cohort_id}/merge")
def merge_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "merged"
        append_audit(session, user.user_id, user.role, "dev", "cohort.merge", "cohort", cohort_id, before=before, after={"status": "merged"})
        session.commit()
        return _cohort_out(session, cohort)

@router.post("/cohorts/{cohort_id}/remedy")
def run_cohort_remedy(cohort_id: str, policy_rule_id: Annotated[str, Query()], user: Annotated[CurrentUser, Depends(current_user)]) -> RemedyComputeOut:
    _require_review_role(user)
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    result = compute_cohort_remedies(session_factory, cohort_id, policy_rule_id)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "cohort.remedy", "cohort", cohort_id, before={}, after=result)
        session.commit()
    return RemedyComputeOut(cohort_id=cohort_id, **result)


# NOTE: split/merge only flip status here. Per §8.2 step 10, split/merge should
# also re-run linking for the affected cohorts; that needs a design decision on
# which cohorts to re-link and is out of scope for this task (not needed for
# demo steps 1-9, which only exercise confirm). Flagged as a follow-up.
