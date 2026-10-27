import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import AuditLog, Cohort, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-review-run"
COHORT_ID = "test-review-cohort"


def _seed(database_url: str, run_id: str = RUN_ID, cohort_id: str = COHORT_ID) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Cohort(id=cohort_id, run_id=run_id, status="proposed", kind="linked"))
        session.commit()


def _teardown(database_url: str, run_id: str, cohort_id: str) -> None:
    with get_session(database_url) as session:
        session.query(AuditLog).filter(AuditLog.target_id == cohort_id).delete()
        cohort = session.get(Cohort, cohort_id)
        if cohort is not None:
            session.delete(cohort)
        run = session.get(PipelineRun, run_id)
        if run is not None:
            session.delete(run)
        session.commit()


def test_agent_cannot_confirm_but_team_lead_can(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)

    try:
        denied = client.post(f"/cohorts/{COHORT_ID}/confirm", headers={"X-Demo-User": "demo-agent"})
        assert denied.status_code == 403

        allowed = client.post(f"/cohorts/{COHORT_ID}/confirm", headers={"X-Demo-User": "demo-team-lead"})
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "confirmed"

        with get_session(database_url_pipeline) as session:
            cohort = session.get(Cohort, COHORT_ID)
            assert cohort.status == "confirmed"
            last_audit = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
            assert last_audit.action == "cohort.confirm"
            assert last_audit.target_id == COHORT_ID
    finally:
        _teardown(database_url_pipeline, RUN_ID, COHORT_ID)


def test_team_lead_can_split_cohort(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    run_id, cohort_id = "test-review-run-split", "test-review-cohort-split"
    _seed(database_url_pipeline, run_id, cohort_id)
    client = TestClient(app)

    try:
        denied = client.post(f"/cohorts/{cohort_id}/split", headers={"X-Demo-User": "demo-agent"})
        assert denied.status_code == 403

        allowed = client.post(f"/cohorts/{cohort_id}/split", headers={"X-Demo-User": "demo-team-lead"})
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "split"

        with get_session(database_url_pipeline) as session:
            cohort = session.get(Cohort, cohort_id)
            assert cohort.status == "split"
            last_audit = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
            assert last_audit.action == "cohort.split"
            assert last_audit.target_id == cohort_id
    finally:
        _teardown(database_url_pipeline, run_id, cohort_id)


def test_compliance_can_merge_cohort(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    run_id, cohort_id = "test-review-run-merge", "test-review-cohort-merge"
    _seed(database_url_pipeline, run_id, cohort_id)
    client = TestClient(app)

    try:
        denied = client.post(f"/cohorts/{cohort_id}/merge", headers={"X-Demo-User": "demo-agent"})
        assert denied.status_code == 403

        allowed = client.post(f"/cohorts/{cohort_id}/merge", headers={"X-Demo-User": "demo-compliance"})
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "merged"

        with get_session(database_url_pipeline) as session:
            cohort = session.get(Cohort, cohort_id)
            assert cohort.status == "merged"
            last_audit = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
            assert last_audit.action == "cohort.merge"
            assert last_audit.target_id == cohort_id
    finally:
        _teardown(database_url_pipeline, run_id, cohort_id)
