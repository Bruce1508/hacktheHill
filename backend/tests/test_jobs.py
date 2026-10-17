import datetime as dt
import os

from backtrace.db import jobs
from backtrace.db.models import Job, PipelineRun
from backtrace.db.session import get_session


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


def test_recover_stale_requeues_a_job_whose_lock_was_never_refreshed():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-jobs-stale-1"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.stage", {}, stage="extraction")
        job.status = "running"
        job.locked_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
        session.commit()
        job_id = job.id

        recovered = jobs.recover_stale(session)
        assert recovered == 1
        assert session.get(Job, job_id).status == "queued"

    _cleanup(database_url, job_id, run_id)


def test_touch_running_keeps_a_long_job_from_being_recovered_as_stale():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-jobs-stale-2"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        job = jobs.enqueue(session, run_id, "pipeline.stage", {}, stage="extraction")
        job.status = "running"
        job.locked_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
        session.commit()
        job_id = job.id

        jobs.touch_running(session, job_id)
        recovered = jobs.recover_stale(session)
        assert recovered == 0
        assert session.get(Job, job_id).status == "running"

    _cleanup(database_url, job_id, run_id)


def test_enqueue_upserts_instead_of_raising_on_existing_run_type_stage():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-jobs-upsert-1"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        first = jobs.enqueue(session, run_id, "pipeline.stage", {"attempt": 1}, stage="extraction")
        first.status = "failed"
        first.attempts = 3
        first.error = "boom"
        session.commit()
        job_id = first.id

        second = jobs.enqueue(session, run_id, "pipeline.stage", {"attempt": 2}, stage="extraction")
        assert second.id == job_id

        refreshed = session.get(Job, job_id)
        assert refreshed.status == "queued"
        assert refreshed.attempts == 0
        assert refreshed.error is None
        assert refreshed.locked_at is None

    _cleanup(database_url, job_id, run_id)


def test_enqueue_upserts_with_null_stage():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-jobs-upsert-2"
    with get_session(database_url) as session:
        _seed_run(session, run_id)
        first = jobs.enqueue(session, run_id, "pipeline.run", {})
        first.status = "done"
        session.commit()
        job_id = first.id

        second = jobs.enqueue(session, run_id, "pipeline.run", {})
        assert second.id == job_id
        assert session.get(Job, job_id).status == "queued"

    _cleanup(database_url, job_id, run_id)
