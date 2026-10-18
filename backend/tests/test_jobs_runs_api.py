import datetime as dt
import os

from backtrace.db.models import Complaint, ComplaintLayout, Customer, Job, PipelineRun
from backtrace.db.session import get_session


def _seed_run_with_layout(session, run_id: str, started_at: dt.datetime, customer_id: str, complaint_id: str) -> None:
    session.merge(Customer(id=customer_id, region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
    session.merge(PipelineRun(run_id=run_id, dataset_profile="dev", dataset_seed=1, config={}, started_at=started_at))
    session.merge(
        Complaint(
            complaint_id=complaint_id,
            customer_id=customer_id,
            received_at=started_at,
            channel="web",
            text="My bill is wrong.",
            product="fiber_basic",
            region="north",
            node_id="node-north-1",
        )
    )
    session.commit()
    session.merge(ComplaintLayout(run_id=run_id, complaint_id=complaint_id, x=0.0, y=0.0, layout_version="pca-svd-v1"))
    session.commit()


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


def test_latest_run_returns_most_recent_run_that_has_layout(client):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id, customer_id, complaint_id = "test-api-run-latest", "test-api-latest-cust-1", "test-api-latest-complaint-1"
    with get_session(database_url) as session:
        _seed_run_with_layout(session, run_id, dt.datetime.now(dt.timezone.utc), customer_id, complaint_id)

    response = client.get("/runs/latest", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id

    with get_session(database_url) as session:
        session.delete(session.get(ComplaintLayout, (run_id, complaint_id)))
        session.delete(session.get(Complaint, complaint_id))
        session.commit()
        session.delete(session.get(PipelineRun, run_id))
        session.delete(session.get(Customer, customer_id))
        session.commit()


def test_latest_run_skips_a_newer_run_with_no_layout_yet(client):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    older_run, newer_run = "test-api-run-older", "test-api-run-newer"
    customer_id, complaint_id = "test-api-older-cust-1", "test-api-older-complaint-1"
    now = dt.datetime.now(dt.timezone.utc)
    with get_session(database_url) as session:
        _seed_run_with_layout(session, older_run, now - dt.timedelta(hours=1), customer_id, complaint_id)
        session.merge(PipelineRun(run_id=newer_run, dataset_profile="dev", dataset_seed=2, config={}, started_at=now))
        session.commit()

    response = client.get("/runs/latest", headers={"X-Demo-User": "demo-agent"})
    assert response.status_code == 200
    assert response.json()["run_id"] == older_run

    with get_session(database_url) as session:
        session.delete(session.get(ComplaintLayout, (older_run, complaint_id)))
        session.delete(session.get(Complaint, complaint_id))
        session.commit()
        session.delete(session.get(PipelineRun, older_run))
        session.delete(session.get(PipelineRun, newer_run))
        session.delete(session.get(Customer, customer_id))
        session.commit()


def test_jobs_and_runs_require_auth(client):
    assert client.get("/jobs/1").status_code == 401
    assert client.get("/runs/latest").status_code == 401
