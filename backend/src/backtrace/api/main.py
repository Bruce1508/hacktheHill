import datetime as dt
import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select

from backtrace.api.auth import CurrentUser, current_user
from backtrace.contracts.complaints import ComplaintOut
from backtrace.contracts.jobs import JobOut, RunOut
from backtrace.db.models import Complaint, Job, PipelineRun, WorkerHeartbeat
from backtrace.db.session import get_session

app = FastAPI(title="Backtrace API")

# Worker heartbeats every 10s (backtrace.worker.main); allow two missed beats
# before calling it dead.
WORKER_HEARTBEAT_STALE_SECONDS = 30


@app.get("/health")
def health() -> dict[str, object]:
    result: dict[str, object] = {"status": "ok"}
    try:
        with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
            heartbeat = session.get(WorkerHeartbeat, True)
    except Exception:
        # API health must not depend on the worker or Gemini being reachable.
        result["worker"] = "unknown"
        return result
    if heartbeat is None:
        result["worker"] = "unknown"
    else:
        age_seconds = (dt.datetime.now(dt.timezone.utc) - heartbeat.updated_at).total_seconds()
        result["worker"] = "alive" if age_seconds < WORKER_HEARTBEAT_STALE_SECONDS else "dead"
        result["worker_heartbeat_age_seconds"] = round(age_seconds, 1)
    return result


@app.get("/jobs/{job_id}")
def get_job(job_id: int, _user: Annotated[CurrentUser, Depends(current_user)]) -> JobOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobOut.model_validate(job)


@app.get("/runs/latest")
def latest_run(_user: Annotated[CurrentUser, Depends(current_user)]) -> RunOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        run = session.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="no runs yet")
        return RunOut.model_validate(run)


@app.get("/complaints")
def list_complaints(
    _user: Annotated[CurrentUser, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[ComplaintOut]:
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        rows = session.execute(
            select(Complaint)
            .order_by(Complaint.received_at, Complaint.complaint_id)
            .limit(limit)
            .offset(offset)
        ).scalars().all()
        return [ComplaintOut.model_validate(row) for row in rows]
