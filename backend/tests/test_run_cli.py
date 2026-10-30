import datetime as dt
import os

import pytest

from backtrace.db import jobs
from backtrace.db.models import Job, PipelineRun
from backtrace.db.session import get_session
from backtrace.pipeline.run_cli import wait_for_run


def _seed_run(session, run_id: str) -> None:
    session.merge(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
    session.commit()


def _cleanup(database_url: str, job_id: int, run_id: str) -> None:
    with get_session(database_url) as session:
        job = session.get(Job, job_id)
        if job is not None:
            session.delete(job)
        run = session.get(PipelineRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def test_wait_for_run_returns_immediately_once_job_is_done():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-done"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.run", {})
        job.status = "done"
        session.commit()
        job_id = job.id

    result = wait_for_run(database_url, run_id, timeout_seconds=5, poll_interval_seconds=0.1)
    assert result.status == "done"

    _cleanup(database_url, job_id, run_id)


def test_wait_for_run_raises_on_failed_job():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-failed"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.run", {})
        job.status = "failed"
        job.error = "boom"
        session.commit()
        job_id = job.id

    with pytest.raises(RuntimeError, match="boom"):
        wait_for_run(database_url, run_id, timeout_seconds=5, poll_interval_seconds=0.1)

    _cleanup(database_url, job_id, run_id)


def test_wait_for_run_times_out_while_still_running():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-timeout"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.run", {})
        job.status = "running"
        session.commit()
        job_id = job.id

    with pytest.raises(TimeoutError):
        wait_for_run(database_url, run_id, timeout_seconds=0.2, poll_interval_seconds=0.1)

    _cleanup(database_url, job_id, run_id)
