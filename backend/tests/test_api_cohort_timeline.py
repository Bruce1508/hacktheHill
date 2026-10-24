import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, Customer, DetectedAnomaly, NetworkNode, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-timeline-run"
COHORT_ID = "test-timeline-cohort"


def _seed(database_url: str) -> None:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=base))
        session.merge(NetworkNode(id="n1", region="north", kind="olt"))
        session.merge(Customer(id="tl-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        for i in range(3):
            session.merge(Complaint(complaint_id=f"tl-complaint-{i}", customer_id="tl-cust", received_at=base + dt.timedelta(minutes=10 * i), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="confirmed", kind="linked"))
        for i in range(3):
            session.merge(CohortMember(run_id=RUN_ID, complaint_id=f"tl-complaint-{i}", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="tl-anomaly", run_id=RUN_ID, node_id="n1", metric="packet_loss_pct", start_at=base, end_at=base + dt.timedelta(hours=1), peak_score=9.0, method="rolling_z_v1"))
        session.merge(CohortEventLink(cohort_id=COHORT_ID, run_id=RUN_ID, anomaly_id="tl-anomaly", overlap_score=5.0, evidence={}))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        session.query(CohortEventLink).filter(CohortEventLink.cohort_id == COHORT_ID).delete()
        session.query(CohortMember).filter(CohortMember.cohort_id == COHORT_ID).delete()
        session.query(Cohort).filter(Cohort.id == COHORT_ID).delete()
        session.query(Complaint).filter(Complaint.complaint_id.like("tl-complaint-%")).delete(synchronize_session=False)
        session.query(DetectedAnomaly).filter(DetectedAnomaly.id == "tl-anomaly").delete()
        session.query(Customer).filter(Customer.id == "tl-cust").delete()
        session.query(PipelineRun).filter(PipelineRun.run_id == RUN_ID).delete()
        session.query(NetworkNode).filter(NetworkNode.id == "n1").delete()
        session.commit()


def test_cohort_timeline_returns_complaint_buckets_and_anomaly_windows(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)

    try:
        resp = client.get(f"/cohorts/{COHORT_ID}/timeline", headers={"X-Demo-User": "demo-agent"})
        assert resp.status_code == 200
        body = resp.json()
        assert sum(b["count"] for b in body["complaint_buckets"]) == 3
        assert body["anomaly_windows"][0]["metric"] == "packet_loss_pct"
    finally:
        _teardown(database_url_pipeline)
