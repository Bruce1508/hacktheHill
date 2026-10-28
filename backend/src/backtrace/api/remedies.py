import datetime as dt
import functools
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backtrace.api.auth import CurrentUser, current_user
from backtrace.audit import append_audit
from backtrace.contracts.remedy import ApprovalOut, GateOut, LetterDraftOut
from backtrace.db.models import Approval, Cohort, Letter, Remedy
from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.rate_limit import RateLimiter
from backtrace.remedy.draft import RemedyAlreadyApproved, draft_letter

router = APIRouter()


@functools.cache
def _rate_limiter(max_calls_per_minute: int) -> RateLimiter:
    # ponytail: one limiter per API process, shared by drafts and gate; the
    # worker paces itself separately, so both together can exceed the cap.
    # A DB-backed shared window is the upgrade if that ever bites.
    return RateLimiter(max_calls_per_minute)


def _get_remedy_or_404(session, remedy_id: str, for_update: bool = False) -> Remedy:
    remedy = session.get(Remedy, remedy_id, with_for_update=for_update) if for_update else session.get(Remedy, remedy_id)
    if remedy is None:
        raise HTTPException(status_code=404, detail="remedy not found")
    return remedy


@router.post("/remedies/{remedy_id}/drafts")
def create_letter_draft(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> LetterDraftOut:
    from backtrace.llm.config import PipelineConfig
    from backtrace.llm.providers import GeminiLetterProvider

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        _get_remedy_or_404(session, remedy_id)
        if session.get(Approval, f"approval-{remedy_id}") is not None:
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="remedy already approved; cannot redraft its letter")
    session_factory = make_session_factory(database_url)
    config = PipelineConfig.load()
    provider = GeminiLetterProvider(config.letter_drafting.model_id, config.letter_drafting.prompt_version)
    try:
        result = draft_letter(session_factory, remedy_id, provider, _rate_limiter(config.max_calls_per_minute))
    except RemedyAlreadyApproved:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="remedy already approved; cannot redraft its letter") from None
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.draft", "remedy", remedy_id, before={}, after=result)
        session.commit()
    return LetterDraftOut(remedy_id=remedy_id, drafted=result["drafted"])


@router.post("/remedies/{remedy_id}/gate")
def run_remedy_gate(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> GateOut:
    from backtrace.gate.consistency import GeminiGateLlmProvider, run_gate
    from backtrace.llm.config import PipelineConfig

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    with get_session(database_url) as session:
        _get_remedy_or_404(session, remedy_id)
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one_or_none()
        if letter is None:
            raise HTTPException(status_code=404, detail="no letter drafted for this remedy yet")
        letter_id = letter.id
    config = PipelineConfig.load()
    provider = GeminiGateLlmProvider(config.gate.model_id, config.gate.prompt_version)
    result = run_gate(session_factory, letter_id, provider, config.gate.forbidden_phrases, _rate_limiter(config.max_calls_per_minute))
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.gate", "letter", letter_id, before={}, after=result)
        session.commit()
    return GateOut(**result)


@router.post("/remedies/{remedy_id}/approve")
def approve_remedy(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> ApprovalOut:
    from backtrace.llm.config import PipelineConfig

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    config = PipelineConfig.load()
    with get_session(database_url) as session:
        remedy = _get_remedy_or_404(session, remedy_id, for_update=True)
        cohort = session.get(Cohort, remedy.cohort_id)
        if cohort.status != "confirmed":
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="cohort must be confirmed before approving remedies")
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one_or_none()
        if letter is None or letter.gate_result is None or letter.gate_result.get("status") != "pass":
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="letter has not passed the Consistency Gate")

        # §12: the threshold is on the cohort's total exposure, not one
        # member's amount — a large cohort of small credits still needs compliance.
        cohort_total = session.execute(select(func.coalesce(func.sum(Remedy.amount), 0)).where(Remedy.cohort_id == remedy.cohort_id)).scalar_one()
        if cohort_total > config.approval_threshold_amount and user.role != "compliance":
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=f"cohorts totalling over {config.approval_threshold_amount} require compliance role")
        if user.role not in {"team_lead", "compliance"}:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires team_lead or compliance")
        if session.get(Approval, f"approval-{remedy_id}") is not None:
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="remedy already approved")

        decided_at = dt.datetime.now(dt.timezone.utc)
        approval = Approval(id=f"approval-{remedy_id}", remedy_id=remedy_id, approver_user_id=user.user_id, role=user.role, auth_mode="dev", mfa_used=False, decision="approved", decided_at=decided_at)
        session.add(approval)  # not merge: the guard above already proved no row exists for this id
        append_audit(session, user.user_id, user.role, "dev", "remedy.approve", "remedy", remedy_id, before={}, after={"decision": "approved", "amount": str(remedy.amount)})
        try:
            session.commit()
        except IntegrityError:
            # The for_update lock above closes this for two requests on this
            # process, but a second process can still race it — the PK
            # conflict means someone else approved first; report it as such.
            session.rollback()
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="remedy already approved") from None
        return ApprovalOut(remedy_id=remedy_id, decision="approved", approver_user_id=user.user_id, role=user.role, decided_at=decided_at)
