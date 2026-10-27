import datetime as dt

from pydantic import BaseModel


class RemedyComputeOut(BaseModel):
    cohort_id: str
    computed: int
    routed_to_individual_review: int


class LetterDraftOut(BaseModel):
    remedy_id: str
    drafted: bool


class ApprovalOut(BaseModel):
    remedy_id: str
    decision: str
    approver_user_id: str
    role: str
    decided_at: dt.datetime
