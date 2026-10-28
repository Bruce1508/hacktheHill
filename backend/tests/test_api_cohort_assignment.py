import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Cohort, CohortMember, Complaint, ComplaintEmbedding, Customer, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-cohort-assign-run"
COHORT_ID = "test-cohort-assign-cohort"


def _vector(primary: float, dimension: int = 768) -> list[float]:
    return [primary] + [0.0] * (dimension - 1)


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="assign-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="assign-member-1", customer_id="assign-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="existing member", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintEmbedding(run_id=RUN_ID, complaint_id="assign-member-1", model_version="fake-embedding-v1", embedding=_vector(1.0)))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked", hypothesis=None, confidence=None))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="assign-member-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))

        for complaint_id, vector in (("assign-near", _vector(0.999)), ("assign-far", _vector(-1.0))):
            session.merge(Complaint(complaint_id=complaint_id, customer_id="assign-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="new", product="fiber_pro", region="north", node_id="n1"))
            session.merge(ComplaintEmbedding(run_id=RUN_ID, complaint_id=complaint_id, model_version="fake-embedding-v1", embedding=vector))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        for complaint_id in ("assign-member-1", "assign-near", "assign-far"):
            for row in (session.get(CohortMember, (RUN_ID, complaint_id)), session.get(ComplaintEmbedding, (RUN_ID, complaint_id))):
                if row is not None:
                    session.delete(row)
        session.commit()

        for complaint_id in ("assign-member-1", "assign-near", "assign-far"):
            session.delete(session.get(Complaint, complaint_id))
        session.delete(session.get(Cohort, COHORT_ID))
        session.delete(session.get(Customer, "assign-cust"))
        session.delete(session.get(PipelineRun, RUN_ID))
        session.commit()


def test_near_complaint_assigned_far_complaint_flagged_new(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)
    headers = {"X-Demo-User": "demo-agent"}

    try:
        near = client.post("/complaints/assign-near/cohort-assignment", headers=headers, params={"run_id": RUN_ID})
        assert near.status_code == 200
        assert near.json() == {"complaint_id": "assign-near", "assigned": True, "cohort_id": COHORT_ID, "similarity": near.json()["similarity"]}
        assert near.json()["similarity"] > 0.99

        far = client.post("/complaints/assign-far/cohort-assignment", headers=headers, params={"run_id": RUN_ID})
        assert far.status_code == 200
        assert far.json() == {"complaint_id": "assign-far", "assigned": False, "cohort_id": None, "similarity": None}

        duplicate = client.post("/complaints/assign-near/cohort-assignment", headers=headers, params={"run_id": RUN_ID})
        assert duplicate.status_code == 409

        with get_session(database_url_pipeline) as session:
            assert session.get(CohortMember, (RUN_ID, "assign-near")).cohort_id == COHORT_ID
            assert session.get(CohortMember, (RUN_ID, "assign-far")) is None
    finally:
        _teardown(database_url_pipeline)


def test_unembedded_complaint_returns_404(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    client = TestClient(app)
    headers = {"X-Demo-User": "demo-agent"}

    response = client.post("/complaints/no-such-complaint/cohort-assignment", headers=headers, params={"run_id": "no-such-run"})

    assert response.status_code == 404
