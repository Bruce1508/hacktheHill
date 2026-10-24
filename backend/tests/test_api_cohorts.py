import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Cohort, CohortMember, Complaint, Customer, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-api-cohorts-run"
COHORT_ID = "test-api-cohorts-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="api-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="api-complaint-1", customer_id="api-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked", hypothesis="test hypothesis", confidence=0.8))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="api-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.commit()


def test_list_and_get_cohort(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)
    headers = {"X-Demo-User": "demo-agent"}

    listed = client.get("/cohorts", headers=headers, params={"run_id": RUN_ID})
    assert listed.status_code == 200
    assert any(c["id"] == COHORT_ID for c in listed.json()["cohorts"])

    detail = client.get(f"/cohorts/{COHORT_ID}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["hypothesis"] == "test hypothesis"

    evidence = client.get(f"/cohorts/{COHORT_ID}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()["sample_complaint_ids"] == ["api-complaint-1"]

    with get_session(database_url_pipeline) as session:
        session.delete(session.get(CohortMember, (RUN_ID, "api-complaint-1")))
        session.delete(session.get(Cohort, COHORT_ID))
        session.delete(session.get(Complaint, "api-complaint-1"))
        session.delete(session.get(Customer, "api-cust"))
        session.delete(session.get(PipelineRun, RUN_ID))
        session.commit()
