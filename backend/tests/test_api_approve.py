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
        session.merge(RemedyPolicy(id="approve-policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="approve-remedy", cohort_id="approve-cohort", complaint_id="approve-complaint", amount=amount, policy_rule_id="approve-policy-outage-credit-v1", policy_version=1, rationale="r"))
        session.merge(Letter(id="approve-letter", remedy_id="approve-remedy", complaint_id="approve-complaint", draft="d", prompt_version="v1", gate_result={"status": gate_status}))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        remedy_ids = ["approve-remedy", "approve-remedy-2"]
        session.query(Approval).filter(Approval.remedy_id.in_(remedy_ids)).delete()
        session.query(Letter).filter(Letter.remedy_id.in_(remedy_ids)).delete()
        session.query(Remedy).filter(Remedy.cohort_id == "approve-cohort").delete()
        session.query(RemedyPolicy).filter(RemedyPolicy.id == "approve-policy-outage-credit-v1").delete()
        session.query(Cohort).filter(Cohort.id == "approve-cohort").delete()
        session.query(Complaint).filter(Complaint.complaint_id.in_(["approve-complaint", "approve-complaint-2"])).delete()
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


def _set_cohort_status(database_url: str, status: str) -> None:
    with get_session(database_url) as session:
        session.get(Cohort, "approve-cohort").status = status
        session.commit()


def test_threshold_applies_to_cohort_total_not_member_amount(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("600.00"), "pass")
    with get_session(database_url_pipeline) as session:
        session.merge(Complaint(complaint_id="approve-complaint-2", customer_id="approve-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Remedy(id="approve-remedy-2", cohort_id="approve-cohort", complaint_id="approve-complaint-2", amount=Decimal("600.00"), policy_rule_id="approve-policy-outage-credit-v1", policy_version=1, rationale="r"))
        session.commit()
    client = TestClient(app)

    try:
        # each member is under the 1000 threshold, but the cohort totals 1200
        resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 403
    finally:
        _teardown(database_url_pipeline)


def test_cannot_approve_when_cohort_not_confirmed(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "pass")
    _set_cohort_status(database_url_pipeline, "proposed")
    client = TestClient(app)

    try:
        resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 409
    finally:
        _teardown(database_url_pipeline)


def test_cannot_compute_remedies_for_unconfirmed_cohort(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "pass")
    _set_cohort_status(database_url_pipeline, "proposed")
    client = TestClient(app)

    try:
        resp = client.post("/cohorts/approve-cohort/remedy", params={"policy_rule_id": "approve-policy-outage-credit-v1"}, headers={"X-Demo-User": "demo-team-lead"})
        assert resp.status_code == 409
    finally:
        _teardown(database_url_pipeline)


def test_missing_inputs_return_404_not_500(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "pass")
    client = TestClient(app, raise_server_exceptions=False)
    lead = {"X-Demo-User": "demo-team-lead"}

    try:
        assert client.post("/cohorts/approve-cohort/remedy", params={"policy_rule_id": "no-such-policy"}, headers=lead).status_code == 404
        # outage policy, but this cohort has no linked event/anomaly to size it
        assert client.post("/cohorts/approve-cohort/remedy", params={"policy_rule_id": "approve-policy-outage-credit-v1"}, headers=lead).status_code == 404
        assert client.post("/remedies/no-such-remedy/drafts", headers=lead).status_code == 404
        assert client.post("/remedies/no-such-remedy/gate", headers=lead).status_code == 404
        with get_session(database_url_pipeline) as session:
            session.query(Letter).filter(Letter.id == "approve-letter").delete()
            session.commit()
        assert client.post("/remedies/approve-remedy/gate", headers=lead).status_code == 404  # gate before any draft
    finally:
        _teardown(database_url_pipeline)
