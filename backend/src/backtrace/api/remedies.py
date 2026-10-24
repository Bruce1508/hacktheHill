import os
from typing import Annotated

from fastapi import APIRouter, Depends

from backtrace.api.auth import CurrentUser, current_user
from backtrace.audit import append_audit
from backtrace.contracts.remedy import LetterDraftOut
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
