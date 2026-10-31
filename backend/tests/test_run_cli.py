import datetime as dt
import os
import threading
import time

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


def test_wait_for_run_raises_value_error_when_no_job_exists():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-no-job"

    with pytest.raises(ValueError, match=run_id):
        wait_for_run(database_url, run_id, timeout_seconds=5, poll_interval_seconds=0.1)


def test_wait_for_run_ignores_a_pipeline_stage_job_for_the_same_run_id():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-wrong-type"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        stage_job = jobs.enqueue(session, run_id, "pipeline.stage", {}, stage="extraction")
        stage_job.status = "done"
        session.commit()
        job_id = stage_job.id

    with pytest.raises(ValueError, match=run_id):
        wait_for_run(database_url, run_id, timeout_seconds=5, poll_interval_seconds=0.1)

    _cleanup(database_url, job_id, run_id)


def test_wait_for_run_picks_up_a_status_change_that_happens_mid_poll():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-run-cli-wait-mid-poll"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.run", {})
        job.status = "running"
        session.commit()
        job_id = job.id

    def _mark_done_shortly() -> None:
        time.sleep(0.3)
        with get_session(database_url) as session:
            session.get(Job, job_id).status = "done"
            session.commit()

    flipper = threading.Thread(target=_mark_done_shortly)
    flipper.start()
    try:
        result = wait_for_run(database_url, run_id, timeout_seconds=5, poll_interval_seconds=0.05)
        assert result.status == "done"
    finally:
        flipper.join()

    _cleanup(database_url, job_id, run_id)
