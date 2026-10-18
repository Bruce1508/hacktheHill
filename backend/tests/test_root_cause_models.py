import datetime as dt
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from backtrace.db.models import (
    Cohort,
    CohortEventLink,
    CohortMember,
    Complaint,
    ComplaintBurst,
    Customer,
    DetectedAnomaly,
    PipelineRun,
    SymptomCluster,
    SymptomClusterMember,
)
from backtrace.db.session import get_session

RUN_ID = "test-root-cause-run-1"
CUSTOMER_ID = "test-root-cause-cust-1"
COMPLAINT_ID = "test-root-cause-complaint-1"


def test_bt_pipeline_can_insert_and_read_each_day3_table():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        session.merge(Customer(id=CUSTOMER_ID, region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(
            Complaint(
                complaint_id=COMPLAINT_ID,
                customer_id=CUSTOMER_ID,
                received_at=dt.datetime.now(dt.timezone.utc),
                channel="web",
                text="My internet is down.",
                product="fiber_basic",
                region="north",
                node_id="node-north-1",
            )
        )
        session.commit()

        now = dt.datetime.now(dt.timezone.utc)
        session.merge(DetectedAnomaly(id="anom-1", run_id=RUN_ID, metric="packet_loss_pct", start_at=now, end_at=now, peak_score=5.0, method="rolling_z_v1"))
        session.merge(ComplaintBurst(id="burst-1", run_id=RUN_ID, region="north", start_at=now, end_at=now, complaint_count=10, peak_score=4.0))
        session.merge(SymptomCluster(id="cluster-1", run_id=RUN_ID, label=0, size=1, method="text"))
        session.merge(SymptomClusterMember(run_id=RUN_ID, complaint_id=COMPLAINT_ID, cluster_id="cluster-1"))
        session.merge(Cohort(id="cohort-1", run_id=RUN_ID, kind="linked"))
        session.merge(CohortMember(cohort_id="cohort-1", complaint_id=COMPLAINT_ID, run_id=RUN_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(CohortEventLink(cohort_id="cohort-1", run_id=RUN_ID, overlap_score=1.0, evidence={}))
        session.commit()

        assert session.get(DetectedAnomaly, "anom-1") is not None
        assert session.get(ComplaintBurst, "burst-1") is not None
        assert session.get(SymptomCluster, "cluster-1") is not None
        assert session.get(SymptomClusterMember, (RUN_ID, COMPLAINT_ID)) is not None
        assert session.get(Cohort, "cohort-1") is not None
        assert session.get(CohortMember, ("cohort-1", COMPLAINT_ID)) is not None
        assert session.execute(text("SELECT count(*) FROM app.cohort_event_links WHERE run_id = :rid"), {"rid": RUN_ID}).scalar() == 1

        session.execute(text("DELETE FROM app.cohort_event_links WHERE run_id = :rid"), {"rid": RUN_ID})
        session.delete(session.get(CohortMember, ("cohort-1", COMPLAINT_ID)))
        session.delete(session.get(Cohort, "cohort-1"))
        session.delete(session.get(SymptomClusterMember, (RUN_ID, COMPLAINT_ID)))
        session.delete(session.get(SymptomCluster, "cluster-1"))
        session.delete(session.get(ComplaintBurst, "burst-1"))
        session.delete(session.get(DetectedAnomaly, "anom-1"))
        session.delete(session.get(Complaint, COMPLAINT_ID))
        session.delete(session.get(PipelineRun, RUN_ID))
        session.delete(session.get(Customer, CUSTOMER_ID))
        session.commit()


def test_bt_pipeline_cannot_select_eval_gold_complaint_labels():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    with get_session(database_url) as session:
        with pytest.raises(ProgrammingError, match="permission denied"):
            session.execute(text("SELECT * FROM eval.gold_complaint_labels LIMIT 1"))
