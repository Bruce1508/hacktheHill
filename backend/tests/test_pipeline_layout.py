import datetime as dt
import math
import os

from backtrace.db.models import Complaint, ComplaintEmbedding, ComplaintLayout, Customer, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.pipeline.layout import LAYOUT_VERSION, run_layout_stage

RUN_ID = "test-layout-run-1"
COMPLAINT_IDS = ["test-layout-complaint-1", "test-layout-complaint-2", "test-layout-complaint-3"]


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(Customer(id="test-layout-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc))
        )
        session.commit()
        for i, cid in enumerate(COMPLAINT_IDS):
            session.merge(
                Complaint(
                    complaint_id=cid,
                    customer_id="test-layout-cust-1",
                    received_at=dt.datetime.now(dt.timezone.utc),
                    channel="web",
                    text=f"complaint {i}",
                    product="fiber_basic",
                    region="north",
                    node_id="node-north-1",
                )
            )
            # distinct, deterministic 768-dim vectors so PCA has real variance to project
            vector = [0.0] * 768
            vector[i] = 1.0
            session.merge(ComplaintEmbedding(run_id=RUN_ID, complaint_id=cid, model_version="fake-embed-v1", embedding=vector))
        session.commit()


def _cleanup(database_url: str) -> None:
    with get_session(database_url) as session:
        for cid in COMPLAINT_IDS:
            layout = session.get(ComplaintLayout, (RUN_ID, cid))
            if layout is not None:
                session.delete(layout)
            emb = session.get(ComplaintEmbedding, (RUN_ID, cid))
            if emb is not None:
                session.delete(emb)
            complaint = session.get(Complaint, cid)
            if complaint is not None:
                session.delete(complaint)
        session.commit()
        session.delete(session.get(PipelineRun, RUN_ID))
        session.delete(session.get(Customer, "test-layout-cust-1"))
        session.commit()


def test_run_layout_stage_produces_finite_coords_for_every_embedded_complaint():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url)
    try:
        session_factory = make_session_factory(database_url)
        result = run_layout_stage(session_factory, RUN_ID)
        assert result == {"processed": 3}

        with get_session(database_url) as session:
            rows = {row.complaint_id: row for row in session.query(ComplaintLayout).filter(ComplaintLayout.run_id == RUN_ID).all()}
        assert set(rows) == set(COMPLAINT_IDS)
        for row in rows.values():
            assert math.isfinite(row.x)
            assert math.isfinite(row.y)
            assert row.layout_version == LAYOUT_VERSION
    finally:
        _cleanup(database_url)


def test_run_layout_stage_overwrites_rather_than_duplicates_on_rerun():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url)
    try:
        session_factory = make_session_factory(database_url)
        run_layout_stage(session_factory, RUN_ID)
        run_layout_stage(session_factory, RUN_ID)

        with get_session(database_url) as session:
            count = session.query(ComplaintLayout).filter(ComplaintLayout.run_id == RUN_ID).count()
        assert count == 3
    finally:
        _cleanup(database_url)
