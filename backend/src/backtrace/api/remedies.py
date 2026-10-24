import datetime as dt
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from backtrace.api.auth import CurrentUser, current_user
from backtrace.audit import append_audit
from backtrace.contracts.remedy import ApprovalOut, LetterDraftOut
from backtrace.db.models import Approval, Letter, Remedy
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.draft import draft_letter

router = APIRouter()


@router.post("/remedies/{remedy_id}/drafts")
def create_letter_draft(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> LetterDraftOut:
    from backtrace.llm.config import PipelineConfig
    from backtrace.llm.providers import GeminiLetterProvider

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    config = PipelineConfig.load()
    provider = GeminiLetterProvider(config.letter_drafting.model_id, config.letter_drafting.prompt_version)
    result = draft_letter(session_factory, remedy_id, provider)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.draft", "remedy", remedy_id, before={}, after=result)
        session.commit()
    return LetterDraftOut(remedy_id=remedy_id, drafted=result["drafted"])


@router.post("/remedies/{remedy_id}/gate")
def run_remedy_gate(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> dict:
    from backtrace.db.models import Letter
    from backtrace.gate.consistency import GeminiGateLlmProvider, run_gate
    from backtrace.llm.config import PipelineConfig

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    with get_session(database_url) as session:
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one()
        letter_id = letter.id
    config = PipelineConfig.load()
    provider = GeminiGateLlmProvider(config.gate.model_id, config.gate.prompt_version)
    result = run_gate(session_factory, letter_id, provider)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.gate", "letter", letter_id, before={}, after=result)
        session.commit()
    return result


@router.post("/remedies/{remedy_id}/approve")
def approve_remedy(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> ApprovalOut:
    from backtrace.llm.config import PipelineConfig

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    config = PipelineConfig.load()
    with get_session(database_url) as session:
        remedy = session.get(Remedy, remedy_id)
        if remedy is None:
            raise HTTPException(status_code=404, detail="remedy not found")
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one_or_none()
        if letter is None or letter.gate_result is None or letter.gate_result.get("status") != "pass":
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="letter has not passed the Consistency Gate")

        if remedy.amount > config.approval_threshold_amount and user.role != "compliance":
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=f"remedies over {config.approval_threshold_amount} require compliance role")
        if user.role not in {"team_lead", "compliance"}:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires team_lead or compliance")

        decided_at = dt.datetime.now(dt.timezone.utc)
        approval = Approval(id=f"approval-{remedy_id}", remedy_id=remedy_id, approver_user_id=user.user_id, role=user.role, auth_mode="dev", mfa_used=False, decision="approved", decided_at=decided_at)
        session.merge(approval)
        append_audit(session, user.user_id, user.role, "dev", "remedy.approve", "remedy", remedy_id, before={}, after={"decision": "approved", "amount": str(remedy.amount)})
        session.commit()
        return ApprovalOut(remedy_id=remedy_id, decision="approved", approver_user_id=user.user_id, role=user.role, decided_at=decided_at)
