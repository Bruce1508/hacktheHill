import datetime as dt
import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backtrace.api import cohorts, remedies
from backtrace.api.auth import CurrentUser, current_user
from backtrace.contracts.complaints import ComplaintOut
from backtrace.contracts.jobs import JobOut, RunOut
from backtrace.contracts.viz import VizComplaintsOut, VizPoint
from backtrace.db.models import Complaint, ComplaintFeatures, ComplaintLayout, Job, PipelineRun, WorkerHeartbeat
from backtrace.db.session import get_session

app = FastAPI(title="Backtrace API")
# The web action panel calls the API from the browser with credentials:
# "include" (demo_user cookie), so the origin must be explicit, never "*".
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(cohorts.router)
app.include_router(remedies.router)

# Worker heartbeats every 10s (backtrace.worker.main); allow two missed beats
# before calling it dead.
WORKER_HEARTBEAT_STALE_SECONDS = 30

# Safety guard on /viz/complaints, not a pagination mechanism (§6.5) — the
# route always returns the whole run's point set.
VIZ_POINTS_MAX = 20_000


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


def _latest_run_with_layout(session) -> PipelineRun | None:
    """A run that's merely enqueued has no layout yet, so it isn't a usable
    "latest run" — picking it would make the scatter (or any other
    per-run view) go empty the moment a new run starts."""
    return session.execute(
        select(PipelineRun)
        .where(PipelineRun.run_id.in_(select(ComplaintLayout.run_id).distinct()))
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@app.get("/runs/latest")
def latest_run(_user: Annotated[CurrentUser, Depends(current_user)]) -> RunOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        run = _latest_run_with_layout(session)
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


@app.get("/viz/complaints")
def viz_complaints(
    _user: Annotated[CurrentUser, Depends(current_user)],
    run_id: str | None = None,
) -> VizComplaintsOut:
    """Whole-run point set for the deck.gl scatter (§6.5) — never paginated
    through /complaints, which is capped at 100 rows for a different use."""
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        run = session.get(PipelineRun, run_id) if run_id else _latest_run_with_layout(session)
        if run is None:
            raise HTTPException(status_code=404, detail="no runs yet")

        rows = session.execute(
            select(ComplaintLayout.complaint_id, ComplaintLayout.x, ComplaintLayout.y, ComplaintFeatures.extraction)
            .join(
                ComplaintFeatures,
                (ComplaintFeatures.run_id == ComplaintLayout.run_id) & (ComplaintFeatures.complaint_id == ComplaintLayout.complaint_id),
            )
            .where(ComplaintLayout.run_id == run.run_id)
            .limit(VIZ_POINTS_MAX)
        ).all()
        points = [
            VizPoint(complaint_id=cid, x=x, y=y, claimed_cause=extraction.get("claimed_cause")) for cid, x, y, extraction in rows
        ]
        return VizComplaintsOut(run_id=run.run_id, dataset_profile=run.dataset_profile, synthetic=True, points=points)
