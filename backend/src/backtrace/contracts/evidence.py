from pydantic import BaseModel


class CohortAssignmentOut(BaseModel):
    complaint_id: str
    assigned: bool
    cohort_id: str | None
    similarity: float | None


class EvidencePack(BaseModel):
    """Real evidence pack for the hypothesis call and the /cohorts/{id}/evidence
    response (§8.2 step 8, §8.3). Replaces EvidencePackStub now that evidence
    linking (Day 3) exists."""

    cohort_id: str
    complaint_ids: list[str]
    event_ids: list[str]
    anomaly_ids: list[str]
    score_components: dict[str, float]  # averaged across cohort_event_links.evidence
    sample_complaint_texts: list[str]  # pii-redacted, capped (see hypothesis.py)


class HypothesisOutput(BaseModel):
    text: str
    cited_complaint_ids: list[str] = []
    cited_event_ids: list[str] = []
    cited_anomaly_ids: list[str] = []


class CohortOut(BaseModel):
    id: str
    run_id: str
    status: str
    kind: str
    hypothesis: str | None
    confidence: float | None
    member_count: int

    model_config = {"from_attributes": True}


class CohortListOut(BaseModel):
    cohorts: list[CohortOut]


class CohortEvidenceOut(BaseModel):
    cohort_id: str
    score_components: dict[str, float]
    hypothesis: str | None
    hypothesis_citations: dict | None
    linked_event_ids: list[str]
    linked_anomaly_ids: list[str]
    sample_complaint_ids: list[str]


class ComplaintBucketOut(BaseModel):
    bucket_start: str
    count: int


class AnomalyWindowOut(BaseModel):
    anomaly_id: str
    metric: str
    start_at: str
    end_at: str
    peak_score: float


class CohortTimelineOut(BaseModel):
    cohort_id: str
    complaint_buckets: list[ComplaintBucketOut]
    anomaly_windows: list[AnomalyWindowOut]
