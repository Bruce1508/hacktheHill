import datetime as dt
import os

import pytest

from backtrace.db.models import Complaint, ComplaintFeatures, Customer, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.providers import FakeExtractionProvider
from backtrace.pipeline.stages import run_extraction_stage

RUN_ID = "test-stages-guard-run-1"
COMPLAINT_ID = "test-stages-guard-complaint-1"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(Customer(id="test-stages-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc))
        )
        session.merge(
            Complaint(
                complaint_id=COMPLAINT_ID,
                customer_id="test-stages-cust-1",
                received_at=dt.datetime.now(dt.timezone.utc),
                channel="web",
                text="My bill is wrong.",
                product="fiber_basic",
                region="north",
                node_id="node-north-1",
            )
        )
        session.commit()


def _cleanup(database_url: str) -> None:
    with get_session(database_url) as session:
        features = session.get(ComplaintFeatures, (RUN_ID, COMPLAINT_ID))
        if features is not None:
            session.delete(features)
        complaint = session.get(Complaint, COMPLAINT_ID)
        if complaint is not None:
            session.delete(complaint)
        session.commit()
        session.delete(session.get(PipelineRun, RUN_ID))
        session.delete(session.get(Customer, "test-stages-cust-1"))
        session.commit()


def test_run_extraction_stage_refuses_to_exceed_max_calls_per_run():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url)
    try:
        session_factory = make_session_factory(database_url)
        with pytest.raises(RuntimeError, match="max_calls_per_run"):
            run_extraction_stage(session_factory, RUN_ID, FakeExtractionProvider(), max_concurrent_calls=4, max_calls_per_run=0)

        with get_session(database_url) as session:
            assert session.get(ComplaintFeatures, (RUN_ID, COMPLAINT_ID)) is None  # guard fired before any provider call
    finally:
        _cleanup(database_url)
