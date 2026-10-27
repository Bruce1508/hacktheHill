import datetime as dt
from decimal import Decimal

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.gate.consistency import FakeGateLlmProvider, run_gate

RUN_ID = "test-gate-run"


def _seed(database_url: str, letter_text: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="gate-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="gate-complaint", customer_id="gate-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="gate-complaint", extraction={"issues": ["no internet for 12 hours"], "vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id="gate-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="gate-policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="gate-remedy", cohort_id="gate-cohort", complaint_id="gate-complaint", amount=Decimal("1.75"), policy_rule_id="gate-policy-outage-credit-v1", policy_version=1, rationale="outage credit"))
        session.merge(Letter(id="gate-letter", remedy_id="gate-remedy", complaint_id="gate-complaint", draft=letter_text, prompt_version="letter-v1", gate_result=None))
        session.commit()


def _teardown(database_url: str) -> None:
    with get_session(database_url) as session:
        session.query(Letter).filter(Letter.id == "gate-letter").delete()
        session.query(Remedy).filter(Remedy.id == "gate-remedy").delete()
        session.query(RemedyPolicy).filter(RemedyPolicy.id == "gate-policy-outage-credit-v1").delete()
        session.query(Cohort).filter(Cohort.id == "gate-cohort").delete()
        session.query(ComplaintFeatures).filter(ComplaintFeatures.run_id == RUN_ID).delete()
        session.query(Complaint).filter(Complaint.complaint_id == "gate-complaint").delete()
        session.query(Customer).filter(Customer.id == "gate-cust").delete()
        session.query(PipelineRun).filter(PipelineRun.run_id == RUN_ID).delete()
        session.commit()


def test_gate_passes_when_amount_matches_and_issues_addressed(database_url_pipeline):
    _seed(database_url_pipeline, "Dear customer, we are issuing a credit of $1.75 for no internet for 12 hours.")
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeGateLlmProvider(fake_all_issues_addressed=True)

    try:
        result = run_gate(session_factory, "gate-letter", provider)

        assert result["status"] == "pass"
        with get_session(database_url_pipeline) as session:
            letter = session.get(Letter, "gate-letter")
            assert letter.gate_result["status"] == "pass"
    finally:
        _teardown(database_url_pipeline)


def test_gate_fails_fast_on_amount_mismatch_without_calling_llm(database_url_pipeline):
    _seed(database_url_pipeline, "Dear customer, we are issuing a credit of $99.00.")
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeGateLlmProvider(fake_all_issues_addressed=True, fail_if_called=True)

    try:
        result = run_gate(session_factory, "gate-letter", provider)

        assert result["status"] == "fail"
        assert "amount" in result["reason"]
    finally:
        _teardown(database_url_pipeline)


def test_regate_of_unchanged_letter_is_served_from_llm_cache(database_url_pipeline):
    _seed(database_url_pipeline, "Dear customer, we are issuing a credit of $1.75 for no internet for 12 hours.")
    session_factory = make_session_factory(database_url_pipeline)

    try:
        run_gate(session_factory, "gate-letter", FakeGateLlmProvider(fake_all_issues_addressed=True))
        result = run_gate(session_factory, "gate-letter", FakeGateLlmProvider(fake_all_issues_addressed=True, fail_if_called=True))

        assert result["status"] == "pass"
    finally:
        _teardown(database_url_pipeline)
