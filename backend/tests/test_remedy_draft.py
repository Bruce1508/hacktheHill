import datetime as dt
from decimal import Decimal

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.draft import FakeLetterProvider, draft_letter

RUN_ID = "test-draft-run"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="draft-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="draft-complaint", customer_id="draft-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="draft-complaint", extraction={"claimed_cause": "outage", "issues": ["no internet for 12 hours"], "vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id="draft-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="draft-remedy", cohort_id="draft-cohort", complaint_id="draft-complaint", amount=Decimal("1.75"), policy_rule_id="policy-outage-credit-v1", policy_version=1, rationale="outage credit"))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        session.query(Letter).filter(Letter.remedy_id == "draft-remedy").delete()
        session.query(Remedy).filter(Remedy.id == "draft-remedy").delete()
        session.query(RemedyPolicy).filter(RemedyPolicy.id == "policy-outage-credit-v1").delete()
        session.query(Cohort).filter(Cohort.id == "draft-cohort").delete()
        session.query(ComplaintFeatures).filter(ComplaintFeatures.run_id == RUN_ID).delete()
        session.query(Complaint).filter(Complaint.complaint_id == "draft-complaint").delete()
        session.query(Customer).filter(Customer.id == "draft-cust").delete()
        session.query(PipelineRun).filter(PipelineRun.run_id == RUN_ID).delete()
        session.commit()


def test_draft_letter_includes_exact_amount(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeLetterProvider()

    try:
        result = draft_letter(session_factory, "draft-remedy", provider)

        assert result["drafted"] is True
        with get_session(database_url_pipeline) as session:
            letter = session.query(Letter).filter(Letter.remedy_id == "draft-remedy").one()
            assert "1.75" in letter.draft
            assert letter.gate_result is None
    finally:
        _teardown(database_url_pipeline)
