import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Approval, Cohort, Complaint, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session

RUN_ID = "test-approve-run"


def _seed(database_url: str, amount: Decimal, gate_status: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="approve-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="approve-complaint", customer_id="approve-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id="approve-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="approve-remedy", cohort_id="approve-cohort", complaint_id="approve-complaint", amount=amount, policy_rule_id="policy-outage-credit-v1", policy_version=1, rationale="r"))
        session.merge(Letter(id="approve-letter", remedy_id="approve-remedy", complaint_id="approve-complaint", draft="d", prompt_version="v1", gate_result={"status": gate_status}))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        session.query(Approval).filter(Approval.remedy_id == "approve-remedy").delete()
        session.query(Letter).filter(Letter.id == "approve-letter").delete()
        session.query(Remedy).filter(Remedy.id == "approve-remedy").delete()
        session.query(RemedyPolicy).filter(RemedyPolicy.id == "policy-outage-credit-v1").delete()
        session.query(Cohort).filter(Cohort.id == "approve-cohort").delete()
        session.query(Complaint).filter(Complaint.complaint_id == "approve-complaint").delete()
        session.query(Customer).filter(Customer.id == "approve-cust").delete()
        session.query(PipelineRun).filter(PipelineRun.run_id == RUN_ID).delete()
        session.commit()


def test_team_lead_can_approve_below_threshold(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "pass")
    client = TestClient(app)

    try:
        resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approved"
    finally:
        _teardown(database_url_pipeline)


def test_team_lead_cannot_approve_above_threshold(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("5000.00"), "pass")
    client = TestClient(app)

    try:
        resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 403

        allowed = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-compliance"})
        assert allowed.status_code == 200
    finally:
        _teardown(database_url_pipeline)


def test_cannot_approve_when_gate_has_not_passed(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "fail")
    client = TestClient(app)

    try:
        resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 409
    finally:
        _teardown(database_url_pipeline)
