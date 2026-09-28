from pydantic import BaseModel


class ComplaintExtraction(BaseModel):
    """Schema-bound output of Gemini structured extraction (§8.2 step 2)."""

    product: str
    symptoms: list[str]
    claimed_cause: str
    issue_start_mentioned: str | None = None
    amounts: list[str] = []
    issues: list[str]
    vulnerability_signals: list[str] = []
    requested_outcome: str | None = None
    identifiers: list[str] = []
