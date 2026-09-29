import datetime as dt
import os

from backtrace.db.models import Complaint, ComplaintFeatures, ComplaintLayout, Customer, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-viz-run-1"
COMPLAINT_ID = "test-viz-complaint-1"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(Customer(id="test-viz-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc))
        )
        session.merge(
            Complaint(
                complaint_id=COMPLAINT_ID,
                customer_id="test-viz-cust-1",
                received_at=dt.datetime.now(dt.timezone.utc),
                channel="web",
                text="My bill is wrong.",
                product="fiber_basic",
                region="north",
                node_id="node-north-1",
            )
        )
        session.commit()
        session.merge(
            ComplaintFeatures(
                run_id=RUN_ID,
                complaint_id=COMPLAINT_ID,
                extraction={"claimed_cause": "billing_error", "symptoms": ["overcharge"]},
                extraction_version="extraction-v1",
                pii_redacted_text="My bill is wrong.",
                needs_review=False,
            )
        )
        session.merge(ComplaintLayout(run_id=RUN_ID, complaint_id=COMPLAINT_ID, x=1.5, y=-2.5, layout_version="pca-svd-v1"))
        session.commit()


def _cleanup(database_url: str) -> None:
    with get_session(database_url) as session:
        layout = session.get(ComplaintLayout, (RUN_ID, COMPLAINT_ID))
        if layout is not None:
            session.delete(layout)
        features = session.get(ComplaintFeatures, (RUN_ID, COMPLAINT_ID))
        if features is not None:
            session.delete(features)
        complaint = session.get(Complaint, COMPLAINT_ID)
        if complaint is not None:
            session.delete(complaint)
        session.commit()
        session.delete(session.get(PipelineRun, RUN_ID))
        session.delete(session.get(Customer, "test-viz-cust-1"))
        session.commit()


def test_viz_complaints_returns_points_with_claimed_cause_and_no_eval_fields(client):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url)
    try:
        response = client.get(f"/viz/complaints?run_id={RUN_ID}", headers={"X-Demo-User": "demo-agent"})
        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == RUN_ID
        assert body["dataset_profile"] == "dev"
        assert body["synthetic"] is True
        points = {p["complaint_id"]: p for p in body["points"]}
        assert points[COMPLAINT_ID]["x"] == 1.5
        assert points[COMPLAINT_ID]["y"] == -2.5
        assert points[COMPLAINT_ID]["claimed_cause"] == "billing_error"
        assert "cohort_id" in points[COMPLAINT_ID] and points[COMPLAINT_ID]["cohort_id"] is None
        assert "gold" not in body and "customer_claimed_cause" not in points[COMPLAINT_ID]
    finally:
        _cleanup(database_url)


def test_viz_complaints_requires_auth(client):
    response = client.get(f"/viz/complaints?run_id={RUN_ID}")
    assert response.status_code == 401
