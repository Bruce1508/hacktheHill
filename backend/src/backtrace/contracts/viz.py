from pydantic import BaseModel


class VizPoint(BaseModel):
    """§6.5 /viz/complaints point. cohort_id/symptom_cluster_id stay null
    until Day 3 linking exists (§Phase 5). claimed_cause is the customer's
    self-reported cause as extracted by the pipeline from complaint text —
    never eval.gold_complaint_labels.customer_claimed_cause, which is
    eval-only and must not leak into an app/API response (§5.6)."""

    complaint_id: str
    x: float
    y: float
    cohort_id: str | None = None
    symptom_cluster_id: str | None = None
    claimed_cause: str | None = None


class VizComplaintsOut(BaseModel):
    run_id: str
    dataset_profile: str
    synthetic: bool
    points: list[VizPoint]
