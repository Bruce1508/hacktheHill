"""Jobs repository (§11): SELECT ... FOR UPDATE SKIP LOCKED claim, bounded
retries, stale-running-job recovery."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backtrace.db.models import Job

MAX_ATTEMPTS = 3
STALE_AFTER = dt.timedelta(minutes=10)


def enqueue(session: Session, run_id: str, type_: str, payload: dict, stage: str | None = None) -> Job:
    """A rerun of the same (run_id, type, stage) hits the unique constraint
    (migration 0003) instead of stacking a second job, so this upserts
    rather than inserts."""
    stmt = (
        pg_insert(Job)
        .values(type=type_, stage=stage, run_id=run_id, payload=payload)
        .on_conflict_do_update(
            constraint="uq_app_jobs_run_type_stage",
            set_={"status": "queued", "attempts": 0, "error": None, "locked_at": None},
        )
        .returning(Job.id)
    )
    job_id = session.execute(stmt).scalar_one()
    session.commit()
    return session.get(Job, job_id)


def claim_next(session: Session) -> Job | None:
    """Claims and commits in one short transaction, releasing the row lock
    before the caller does any slow work (§Phase 4 guard)."""
    stmt = select(Job).where(Job.status == "queued").order_by(Job.id).with_for_update(skip_locked=True).limit(1)
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        session.commit()
        return None
    job.status = "running"
    job.locked_at = dt.datetime.now(dt.timezone.utc)
    job.attempts += 1
    job.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return job


def mark_done(session: Session, job: Job) -> None:
    job.status = "done"
    job.error = None
    job.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


def mark_failed(session: Session, job: Job, error: str) -> None:
    job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
    job.error = error
    job.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()


def recover_stale(session: Session) -> int:
    """A job stuck 'running' past STALE_AFTER (its worker died) goes back to
    queued for another attempt, up to MAX_ATTEMPTS, else failed."""
    cutoff = dt.datetime.now(dt.timezone.utc) - STALE_AFTER
    stmt = select(Job).where(Job.status == "running", Job.locked_at < cutoff).with_for_update(skip_locked=True)
    stale = session.execute(stmt).scalars().all()
    for job in stale:
        job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
        job.error = "recovered from stale running state"
        job.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return len(stale)
