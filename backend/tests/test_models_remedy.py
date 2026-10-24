import datetime as dt
from decimal import Decimal

from backtrace.db.models import Approval, AuditLog, Cohort, Complaint, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session


def test_remedy_review_tables_round_trip(database_url_pipeline):
    with get_session(database_url_pipeline) as session:
        session.merge(PipelineRun(run_id="test-remedy-models", dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="test-remedy-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="test-remedy-complaint", customer_id="test-remedy-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id="test-remedy-cohort", run_id="test-remedy-models", status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.commit()

        session.merge(Remedy(id="remedy-1", cohort_id="test-remedy-cohort", complaint_id="test-remedy-complaint", amount=Decimal("3.50"), policy_rule_id="policy-outage-v1", policy_version=1, rationale="outage credit"))
        session.commit()

        session.merge(Letter(id="letter-1", remedy_id="remedy-1", complaint_id="test-remedy-complaint", draft="Dear customer...", prompt_version="letter-v1", gate_result=None))
        session.commit()

        session.merge(Approval(id="approval-1", remedy_id="remedy-1", approver_user_id="demo-team-lead", role="team_lead", auth_mode="dev", mfa_used=False, decision="approved", decided_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(AuditLog(actor_user_id="demo-team-lead", role="team_lead", auth_mode="dev", action="remedy.approve", target_type="remedy", target_id="remedy-1", before={}, after={"decision": "approved"}, prev_hash=None, hash="x" * 64))
        session.commit()

        assert session.get(Remedy, "remedy-1").amount == Decimal("3.50")
        assert session.get(Letter, "letter-1").gate_result is None
        assert session.get(Approval, "approval-1").decision == "approved"
