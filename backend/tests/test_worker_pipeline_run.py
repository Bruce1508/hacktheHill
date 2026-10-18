import datetime as dt
import os

from sqlalchemy import delete, select, text

from backtrace.db.models import (
    Cohort,
    CohortEventLink,
    CohortMember,
    Complaint,
    ComplaintBurst,
    ComplaintEmbedding,
    ComplaintFeatures,
    ComplaintLayout,
    Customer,
    DetectedAnomaly,
    NetworkNode,
    PipelineRun,
    SymptomCluster,
    SymptomClusterMember,
    Telemetry,
)
from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.config import PipelineConfig
from backtrace.llm.providers import FakeEmbeddingProvider, FakeExtractionProvider
from backtrace.worker.main import _run_job

RUN_ID_A = "test-worker-pipeline-run-a"
NODE_ID = "test-worker-node-north"
CUSTOMER_ID = "test-worker-cust-north"
SPIKE_AT = dt.datetime(2026, 1, 2, 1, 0, tzinfo=dt.timezone.utc)
COMPLAINT_IDS = [f"test-worker-complaint-{i}" for i in range(5)]


def _seed(database_url: str, run_id: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(NetworkNode(id=NODE_ID, region="north", kind="olt"))
        session.merge(Customer(id=CUSTOMER_ID, region="north", plan="fiber_basic", segment="residential", node_id=NODE_ID))

        # 48 clean samples (anomaly.py's window_points) then 2 spike samples —
        # zero-variance baseline makes the spike an immediate z=inf anomaly.
        for i in range(50):
            sampled_at = SPIKE_AT - dt.timedelta(minutes=50 - i)
            spiking = i >= 48
            session.merge(
                Telemetry(
                    node_id=NODE_ID, link_id=None, sampled_at=sampled_at,
                    optical_power_dbm=-20.0, errored_seconds=0,
                    packet_loss_pct=95.0 if spiking else 0.1,
                    latency_ms=5.0, alarm=spiking,
                )
            )

        for i, complaint_id in enumerate(COMPLAINT_IDS):
            session.merge(
                Complaint(
                    complaint_id=complaint_id, customer_id=CUSTOMER_ID,
                    received_at=SPIKE_AT + dt.timedelta(minutes=i),
                    channel="web", text="My internet keeps dropping out in the north region.",
                    product="fiber_basic", region="north", node_id=NODE_ID,
                )
            )
        session.commit()


def _cleanup_run_scoped(database_url: str, run_id: str) -> None:
    with get_session(database_url) as session:
        session.execute(delete(CohortMember).where(CohortMember.run_id == run_id))
        session.execute(delete(CohortEventLink).where(CohortEventLink.run_id == run_id))
        session.execute(delete(Cohort).where(Cohort.run_id == run_id))
        session.execute(delete(SymptomClusterMember).where(SymptomClusterMember.run_id == run_id))
        session.execute(delete(SymptomCluster).where(SymptomCluster.run_id == run_id))
        session.execute(delete(DetectedAnomaly).where(DetectedAnomaly.run_id == run_id))
        session.execute(delete(ComplaintBurst).where(ComplaintBurst.run_id == run_id))
        session.execute(delete(ComplaintLayout).where(ComplaintLayout.run_id == run_id))
        session.execute(delete(ComplaintEmbedding).where(ComplaintEmbedding.run_id == run_id))
        session.execute(delete(ComplaintFeatures).where(ComplaintFeatures.run_id == run_id))
        session.execute(text("DELETE FROM app.llm_calls WHERE run_id = :rid"), {"rid": run_id})
        session.execute(delete(PipelineRun).where(PipelineRun.run_id == run_id))
        session.commit()


def _cleanup_shared(database_url: str) -> None:
    with get_session(database_url) as session:
        for complaint_id in COMPLAINT_IDS:
            session.execute(delete(Complaint).where(Complaint.complaint_id == complaint_id))
        session.execute(delete(Customer).where(Customer.id == CUSTOMER_ID))
        session.execute(delete(Telemetry).where(Telemetry.node_id == NODE_ID))
        session.execute(delete(NetworkNode).where(NetworkNode.id == NODE_ID))
        session.commit()


class _Job:
    def __init__(self, run_id: str, job_type: str):
        self.id = -1
        self.run_id = run_id
        self.type = job_type
        self.stage = None


def test_pipeline_run_completes_all_seven_stages_and_populates_every_new_table():
    # extraction/embedding are scoped to every app.complaints row lacking
    # features for this run_id (pre-existing Day 2 design), not to a bespoke
    # subset — so this run processes the whole shared dev fixture, not just
    # the 5 complaints seeded below. Run-wide tables are asserted >=1;
    # per-complaint tables are asserted exactly against our own ids.
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url, RUN_ID_A)
    session_factory = make_session_factory(database_url)
    config = PipelineConfig.load()

    try:
        _run_job(session_factory, config, FakeExtractionProvider(), FakeEmbeddingProvider(dimension=config.embedding.output_dimensionality), _Job(RUN_ID_A, "pipeline.run"))

        with get_session(database_url) as session:
            def count(model, run_id=RUN_ID_A):
                return session.execute(select(model).where(model.run_id == run_id)).all()

            def count_mine(model):
                return session.execute(select(model).where(model.run_id == RUN_ID_A, model.complaint_id.in_(COMPLAINT_IDS))).all()

            assert len(count_mine(ComplaintFeatures)) == len(COMPLAINT_IDS)
            assert len(count_mine(ComplaintEmbedding)) == len(COMPLAINT_IDS)
            assert len(count_mine(SymptomClusterMember)) == len(COMPLAINT_IDS)
            assert len(count_mine(ComplaintLayout)) == len(COMPLAINT_IDS)
            assert len(count(DetectedAnomaly)) >= 1
            assert len(count(ComplaintBurst)) >= 1
            assert len(count(CohortMember)) >= 1
            assert len(count(Cohort)) >= 1
            assert len(count(CohortEventLink)) >= 1
    finally:
        _cleanup_run_scoped(database_url, RUN_ID_A)
        _cleanup_shared(database_url)
