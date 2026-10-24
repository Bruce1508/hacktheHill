import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import AuditLog, Cohort, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-review-run"
COHORT_ID = "test-review-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked"))
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
        with get_session(database_url_pipeline) as session:
            session.query(AuditLog).filter(AuditLog.target_id == COHORT_ID).delete()
            cohort = session.get(Cohort, COHORT_ID)
            if cohort is not None:
                session.delete(cohort)
            run = session.get(PipelineRun, RUN_ID)
            if run is not None:
                session.delete(run)
            session.commit()
