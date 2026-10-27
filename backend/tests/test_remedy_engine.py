import datetime as dt

from sqlalchemy import select

from backtrace.db.models import Approval, Cohort, CohortEventLink, CohortMember, Complaint, ComplaintFeatures, Customer, DetectedAnomaly, Letter, NetworkNode, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.engine import compute_cohort_remedies

RUN_ID = "test-remedy-engine-run"
COHORT_ID = "test-remedy-engine-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(NetworkNode(id="eng-node-1", region="north", kind="olt"))
        session.merge(Customer(id="eng-cust-1", region="north", plan="fiber_pro", segment="residential", node_id="eng-node-1"))
        session.merge(Customer(id="eng-cust-2", region="north", plan="fiber_pro", segment="residential", node_id="eng-node-1"))
        session.merge(Complaint(complaint_id="eng-complaint-1", customer_id="eng-cust-1", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="eng-node-1"))
        session.merge(Complaint(complaint_id="eng-complaint-2", customer_id="eng-cust-2", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="eng-node-1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="eng-complaint-1", extraction={"vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="eng-complaint-2", extraction={"vulnerability_signals": ["hardship"]}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="eng-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="eng-complaint-2", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="eng-anomaly-1", run_id=RUN_ID, node_id="eng-node-1", metric="packet_loss_pct", start_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), end_at=dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc), peak_score=9.0, method="rolling_z_v1"))
        session.merge(RemedyPolicy(id="eng-policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.commit()
        existing_link = session.execute(select(CohortEventLink).where(CohortEventLink.cohort_id == COHORT_ID, CohortEventLink.anomaly_id == "eng-anomaly-1")).scalar_one_or_none()
        if existing_link is None:
            session.add(CohortEventLink(cohort_id=COHORT_ID, run_id=RUN_ID, anomaly_id="eng-anomaly-1", overlap_score=1.0, evidence={}))
            session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        remedy_ids = select(Remedy.id).where(Remedy.cohort_id == COHORT_ID)
        session.query(Approval).filter(Approval.remedy_id.in_(remedy_ids)).delete(synchronize_session=False)
        session.query(Letter).filter(Letter.remedy_id.in_(remedy_ids)).delete(synchronize_session=False)
        session.query(Remedy).filter(Remedy.cohort_id == COHORT_ID).delete()
        session.query(CohortEventLink).filter(CohortEventLink.cohort_id == COHORT_ID).delete()
        session.query(CohortMember).filter(CohortMember.cohort_id == COHORT_ID).delete()
        session.query(Cohort).filter(Cohort.id == COHORT_ID).delete()
        session.query(ComplaintFeatures).filter(ComplaintFeatures.run_id == RUN_ID).delete()
        session.query(Complaint).filter(Complaint.complaint_id.in_(["eng-complaint-1", "eng-complaint-2"])).delete()
        session.query(Customer).filter(Customer.id.in_(["eng-cust-1", "eng-cust-2"])).delete()
        session.query(DetectedAnomaly).filter(DetectedAnomaly.id == "eng-anomaly-1").delete()
        session.query(RemedyPolicy).filter(RemedyPolicy.id == "eng-policy-outage-credit-v1").delete()
        session.query(PipelineRun).filter(PipelineRun.run_id == RUN_ID).delete()
        session.query(NetworkNode).filter(NetworkNode.id == "eng-node-1").delete()
        session.commit()


def test_compute_cohort_remedies_skips_vulnerable_member(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)

    try:
        result = compute_cohort_remedies(session_factory, COHORT_ID, "eng-policy-outage-credit-v1")

        assert result["computed"] == 1
        assert result["routed_to_individual_review"] == 1
        assert result["remedy_ids"] == [f"{COHORT_ID}-eng-complaint-1"]
        with get_session(database_url_pipeline) as session:
            remedies = session.query(Remedy).filter(Remedy.cohort_id == COHORT_ID).all()
            assert len(remedies) == 1
            assert remedies[0].complaint_id == "eng-complaint-1"
    finally:
        _teardown(database_url_pipeline)


def test_recompute_after_letter_and_approval_exist(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    remedy_id = f"{COHORT_ID}-eng-complaint-1"

    try:
        compute_cohort_remedies(session_factory, COHORT_ID, "eng-policy-outage-credit-v1")
        with get_session(database_url_pipeline) as session:
            session.add(Letter(id="eng-letter-1", remedy_id=remedy_id, complaint_id="eng-complaint-1", draft="d", prompt_version="letter-v1", gate_result={"status": "pass"}))
            session.flush()
            session.add(Approval(id="eng-approval-1", remedy_id=remedy_id, approver_user_id="demo-team-lead", role="team_lead", auth_mode="dev", mfa_used=False, decision="approved", decided_at=dt.datetime.now(dt.timezone.utc)))
            session.commit()

        result = compute_cohort_remedies(session_factory, COHORT_ID, "eng-policy-outage-credit-v1")  # must not raise IntegrityError

        assert result["remedy_ids"] == [remedy_id]
        with get_session(database_url_pipeline) as session:
            assert session.get(Letter, "eng-letter-1") is None
            assert session.get(Approval, "eng-approval-1") is None
    finally:
        _teardown(database_url_pipeline)
