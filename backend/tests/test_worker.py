import datetime as dt
import os

from backtrace.db import jobs
from backtrace.db.models import Job, PipelineRun, WorkerHeartbeat
from backtrace.db.session import get_session, make_session_factory
from backtrace.worker.main import _heartbeat_and_touch_job


def test_heartbeat_and_touch_job_refreshes_both_rows_during_a_long_job():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-worker-heartbeat-1"
    session_factory = make_session_factory(database_url)

    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        job = jobs.enqueue(session, run_id, "pipeline.stage", {}, stage="extraction")
        job.status = "running"
        job.locked_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)
        session.commit()
        job_id = job.id

    _heartbeat_and_touch_job(session_factory, job_id)

    with get_session(database_url) as session:
        refreshed_job = session.get(Job, job_id)
        heartbeat = session.get(WorkerHeartbeat, True)
        now = dt.datetime.now(dt.timezone.utc)
        assert (now - refreshed_job.locked_at.replace(tzinfo=dt.timezone.utc)) < dt.timedelta(seconds=30)
        assert (now - heartbeat.updated_at.replace(tzinfo=dt.timezone.utc)) < dt.timedelta(seconds=30)

        session.delete(refreshed_job)
        session.delete(session.get(PipelineRun, run_id))
        session.commit()
