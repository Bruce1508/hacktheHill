import datetime as dt
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

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
        session.merge(CohortMember(run_id=RUN_ID, complaint_id=COMPLAINT_ID, cohort_id="cohort-1", membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(CohortEventLink(cohort_id="cohort-1", run_id=RUN_ID, anomaly_id="anom-1", overlap_score=1.0, evidence={}))
        session.commit()

        assert session.get(DetectedAnomaly, "anom-1") is not None
        assert session.get(ComplaintBurst, "burst-1") is not None
        assert session.get(SymptomCluster, "cluster-1") is not None
        assert session.get(SymptomClusterMember, (RUN_ID, COMPLAINT_ID)) is not None
        assert session.get(Cohort, "cohort-1") is not None
        assert session.get(CohortMember, (RUN_ID, COMPLAINT_ID)) is not None
        assert session.execute(text("SELECT count(*) FROM app.cohort_event_links WHERE run_id = :rid"), {"rid": RUN_ID}).scalar() == 1

        session.execute(text("DELETE FROM app.cohort_event_links WHERE run_id = :rid"), {"rid": RUN_ID})
        session.delete(session.get(CohortMember, (RUN_ID, COMPLAINT_ID)))
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


def test_a_complaint_cannot_belong_to_two_cohorts_in_the_same_run():
    # §8.3: a complaint is assigned to exactly one (highest-scoring)
    # candidate, so cohort_members' PK is (run_id, complaint_id) — a second
    # cohort assignment for the same complaint must upsert, not insert twice.
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id, customer_id, complaint_id = "test-rc-onecohort-run", "test-rc-onecohort-cust", "test-rc-onecohort-complaint"
    with get_session(database_url) as session:
        session.merge(Customer(id=customer_id, region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(
            Complaint(
                complaint_id=complaint_id, customer_id=customer_id, received_at=dt.datetime.now(dt.timezone.utc),
                channel="web", text="x", product="fiber_basic", region="north", node_id="node-north-1",
            )
        )
        session.merge(Cohort(id="test-rc-onecohort-a", run_id=run_id, kind="linked"))
        session.merge(Cohort(id="test-rc-onecohort-b", run_id=run_id, kind="linked"))
        session.commit()

        session.merge(CohortMember(run_id=run_id, complaint_id=complaint_id, cohort_id="test-rc-onecohort-a", membership_score=1.0, assigned_by="batch", needs_review=False))
        session.commit()
        session.merge(CohortMember(run_id=run_id, complaint_id=complaint_id, cohort_id="test-rc-onecohort-b", membership_score=2.0, assigned_by="batch", needs_review=False))
        session.commit()

        assert session.get(CohortMember, (run_id, complaint_id)).cohort_id == "test-rc-onecohort-b"
        assert session.execute(text("SELECT count(*) FROM app.cohort_members WHERE run_id = :rid"), {"rid": run_id}).scalar() == 1

        session.delete(session.get(CohortMember, (run_id, complaint_id)))
        session.delete(session.get(Cohort, "test-rc-onecohort-a"))
        session.delete(session.get(Cohort, "test-rc-onecohort-b"))
        session.delete(session.get(Complaint, complaint_id))
        session.delete(session.get(PipelineRun, run_id))
        session.delete(session.get(Customer, customer_id))
        session.commit()


def test_cohort_event_link_requires_an_event_or_anomaly():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "test-rc-evidence-run"
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Cohort(id="test-rc-evidence-cohort", run_id=run_id, kind="linked"))
        session.commit()

        session.add(CohortEventLink(cohort_id="test-rc-evidence-cohort", run_id=run_id, overlap_score=1.0, evidence={}))
        with pytest.raises(IntegrityError, match="ck_app_cohort_event_links_has_evidence"):
            session.commit()
        session.rollback()

        session.delete(session.get(Cohort, "test-rc-evidence-cohort"))
        session.delete(session.get(PipelineRun, run_id))
        session.commit()
