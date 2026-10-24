from pydantic import BaseModel


class RemedyComputeOut(BaseModel):
    cohort_id: str
    computed: int
    routed_to_individual_review: int
