import datetime as dt

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    type: str
    stage: str | None
    run_id: str
    status: str
    attempts: int
    error: str | None
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    run_id: str
    dataset_profile: str
    dataset_seed: int
    started_at: dt.datetime
    finished_at: dt.datetime | None

    model_config = {"from_attributes": True}
