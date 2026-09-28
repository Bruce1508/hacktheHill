from pydantic import BaseModel


class EvidencePackStub(BaseModel):
    """Placeholder shape for the hypothesis evidence pack (§8.2 step 8).

    Filled in with real linking-score components once evidence linking
    (§8.3) exists — Day 3 work. Kept here now only so the contracts
    package matches the Day 1 scope item in §19.
    """

    cohort_id: str
    complaint_ids: list[str]
    event_ids: list[str]
    anomaly_ids: list[str]
