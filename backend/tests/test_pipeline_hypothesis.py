# backend/tests/test_pipeline_hypothesis.py
import datetime as dt

from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, Customer, DetectedAnomaly, NetworkNode, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.pipeline.hypothesis import FakeHypothesisProvider, build_evidence_pack, run_hypothesis_stage

RUN_ID = "test-hypothesis-run"
COHORT_ID = "test-hypothesis-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="hyp-cust", region="north", plan="fiber_pro", segment="residential", node_id="hyp-node"))
        session.merge(NetworkNode(id="hyp-node", region="north", kind="olt"))
        session.merge(Complaint(complaint_id="hyp-complaint-1", customer_id="hyp-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="internet is down", product="fiber_pro", region="north", node_id="hyp-node"))
        # Explicit None: session.merge() leaves an attribute untouched on an
        # existing row when the source object never set it, so a prior test's
        # accepted hypothesis would otherwise bleed into this run (DB rows
        # here are not torn down between tests).
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked", hypothesis=None, hypothesis_citations=None, confidence=None))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="hyp-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="hyp-anomaly-1", run_id=RUN_ID, node_id="hyp-node", metric="packet_loss_pct", start_at=dt.datetime.now(dt.timezone.utc), end_at=dt.datetime.now(dt.timezone.utc), peak_score=9.0, method="rolling_z_v1"))
        session.merge(CohortEventLink(cohort_id=COHORT_ID, run_id=RUN_ID, anomaly_id="hyp-anomaly-1", overlap_score=5.0, evidence={"telemetry": 1.0}))
        session.commit()


def test_build_evidence_pack_includes_real_ids(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    with session_factory() as session:
        pack = build_evidence_pack(session, COHORT_ID)
    assert pack.cohort_id == COHORT_ID
    assert pack.complaint_ids == ["hyp-complaint-1"]
    assert pack.anomaly_ids == ["hyp-anomaly-1"]


def test_run_hypothesis_stage_rejects_uncited_ids(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeHypothesisProvider(fake_cited_complaint_ids=["not-a-real-id"])
    result = run_hypothesis_stage(session_factory, RUN_ID, provider)
    assert result["rejected"] == 1
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.hypothesis is None  # invalid citation -> not shown (§8.2 step 8)


def test_run_hypothesis_stage_accepts_valid_citations(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeHypothesisProvider(fake_cited_complaint_ids=["hyp-complaint-1"], fake_cited_anomaly_ids=["hyp-anomaly-1"])
    result = run_hypothesis_stage(session_factory, RUN_ID, provider)
    assert result["accepted"] == 1
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.hypothesis is not None
        assert cohort.hypothesis_citations["complaint_ids"] == ["hyp-complaint-1"]


def test_run_hypothesis_stage_clears_stale_hypothesis_on_rerun_rejection(database_url_pipeline):
    """A prior run accepted a hypothesis citing hyp-complaint-1. On rerun,
    cohort membership has changed such that the new citation check rejects
    the new output — the old accepted hypothesis must not survive on the
    row (§8.2 step 8's "never shown" guarantee must hold on rerun, not just
    on first run)."""
    _seed(database_url_pipeline)
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        cohort.hypothesis = "Stale hypothesis from a previous run."
        cohort.hypothesis_citations = {"complaint_ids": ["hyp-complaint-1"], "event_ids": [], "anomaly_ids": ["hyp-anomaly-1"]}
        cohort.confidence = 1.0
        session.commit()

    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeHypothesisProvider(fake_cited_complaint_ids=["not-a-real-id"])
    result = run_hypothesis_stage(session_factory, RUN_ID, provider)
    assert result["rejected"] == 1
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.hypothesis is None
        assert cohort.hypothesis_citations is None
        assert cohort.confidence is None
