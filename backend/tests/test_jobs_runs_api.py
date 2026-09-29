import datetime as dt
import os

from backtrace.db.models import Job, PipelineRun
from backtrace.db.session import get_session


def test_get_job_returns_seeded_job(client):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id="test-api-run-1", dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()
        job = Job(type="pipeline.stage", stage="extraction", run_id="test-api-run-1", payload={})
        session.add(job)
        session.commit()
        job_id = job.id

    response = client.get(f"/jobs/{job_id}", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["run_id"] == "test-api-run-1"
    assert body["status"] == "queued"

    with get_session(database_url) as session:
        session.delete(session.get(Job, job_id))
        session.delete(session.get(PipelineRun, "test-api-run-1"))
        session.commit()


def test_get_job_404_for_missing_id(client):
    response = client.get("/jobs/999999999", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 404


def test_latest_run_returns_most_recent(client):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(
            PipelineRun(
                run_id="test-api-run-latest",
                dataset_profile="dev",
                dataset_seed=42,
                config={},
                started_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        session.commit()

    response = client.get("/runs/latest", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 200
    body = response.json()
    assert "run_id" in body

    with get_session(database_url) as session:
        session.delete(session.get(PipelineRun, "test-api-run-latest"))
        session.commit()


def test_jobs_and_runs_require_auth(client):
    assert client.get("/jobs/1").status_code == 401
    assert client.get("/runs/latest").status_code == 401
