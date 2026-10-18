import datetime as dt
import os

import numpy as np
from sqlalchemy import text

from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.config import LinkParams, PipelineConfig
from backtrace.pipeline.clustering import run_clustering_stage
from backtrace.pipeline.linking import Candidate, ComplaintCtx, assign, group_candidates, run_linking_stage, score_components, total_score

CONFIG_PARAMS = PipelineConfig.load().linking
T0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _ctx(node_id="node-A", region="north", received_at=T0, vector=None, cluster_id=None, customer_id="cust-1"):
    return ComplaintCtx(
        complaint_id="c1", customer_id=customer_id, region=region, node_id=node_id,
        received_at=received_at, vector=vector if vector is not None else np.zeros(8), cluster_id=cluster_id,
    )


def test_complaint_inside_event_window_with_overlapping_anomaly_scores_full_temporal_and_telemetry():
    event = Candidate(id="event-1", kind="event", start_at=T0, end_at=T0 + dt.timedelta(hours=1), region="north", node_ids=frozenset(), customer_ids=None)
    anomaly = Candidate(id="anomaly-1", kind="anomaly", start_at=T0, end_at=T0 + dt.timedelta(hours=1), region="north", node_ids=frozenset({"node-A"}), customer_ids=None)
    c = _ctx(received_at=T0 + dt.timedelta(minutes=10))

    components = score_components(c, event, anomalies=[anomaly], bursts=[], centroid=None, params=CONFIG_PARAMS)

    assert components["temporal"] == 1.0
    assert components["telemetry"] == 1.0

    groups = group_candidates([event, anomaly])
    assert len(groups) == 1
    assert groups[0] == frozenset({"event-1", "anomaly-1"})


def test_overlap_case_complaint_off_the_anomalous_node_is_never_silently_merged():
    event = Candidate(id="event-1", kind="event", start_at=T0, end_at=T0 + dt.timedelta(hours=1), region="north", node_ids=frozenset(), customer_ids=None)
    anomaly_a = Candidate(id="anomaly-1", kind="anomaly", start_at=T0, end_at=T0 + dt.timedelta(hours=1), region="north", node_ids=frozenset({"node-A"}), customer_ids=None)
    candidates = [event, anomaly_a]

    complaint_a = _ctx(node_id="node-A", received_at=T0 + dt.timedelta(minutes=10))
    scores_a = {cand.id: total_score(score_components(complaint_a, cand, anomalies=[anomaly_a], bursts=[], centroid=None, params=CONFIG_PARAMS), CONFIG_PARAMS.weights) for cand in candidates}
    best_a, _ = assign(scores_a, CONFIG_PARAMS)
    assert best_a == "anomaly-1"

    complaint_b = _ctx(node_id="node-B", received_at=T0 + dt.timedelta(minutes=10))
    scores_b = {cand.id: total_score(score_components(complaint_b, cand, anomalies=[anomaly_a], bursts=[], centroid=None, params=CONFIG_PARAMS), CONFIG_PARAMS.weights) for cand in candidates}
    best_b, _ = assign(scores_b, CONFIG_PARAMS)
    assert best_b != "anomaly-1"


def test_temporal_decays_after_end_at_and_is_zero_before_start_at():
    params = LinkParams(weights={}, threshold=0, ambiguity_margin=0, lag_max_minutes=720, temporal_tau_minutes=180)
    cand = Candidate(id="e", kind="event", start_at=T0, end_at=T0, region="north", node_ids=frozenset(), customer_ids=None)

    after = score_components(_ctx(received_at=T0 + dt.timedelta(hours=2)), cand, anomalies=[], bursts=[], centroid=None, params=params)
    assert after["temporal"] == np.exp(-120 / 180)

    before = score_components(_ctx(received_at=T0 - dt.timedelta(minutes=1)), cand, anomalies=[], bursts=[], centroid=None, params=params)
    assert before["temporal"] == 0.0


def test_semantic_only_match_never_reaches_threshold_with_config_weights():
    cand = Candidate(id="e", kind="event", start_at=T0 + dt.timedelta(days=10), end_at=T0 + dt.timedelta(days=10), region="south", node_ids=frozenset(), customer_ids=None)
    vector = np.array([1.0, 0.0, 0.0])
    c = _ctx(node_id="node-Z", region="north", received_at=T0, vector=vector)

    components = score_components(c, cand, anomalies=[], bursts=[], centroid=vector, params=CONFIG_PARAMS)
    assert components["semantic"] == 1.0
    assert all(v == 0.0 for k, v in components.items() if k != "semantic")

    score = total_score(components, CONFIG_PARAMS.weights)
    best, _ = assign({"e": score}, CONFIG_PARAMS)
    assert best is None


def test_assign_flags_ambiguous_ties_and_rejects_below_threshold():
    params = LinkParams(weights={}, threshold=4.0, ambiguity_margin=0.5, lag_max_minutes=0, temporal_tau_minutes=1)

    assert assign({"e1": 5.0, "e2": 4.8}, params) == ("e1", True)
    assert assign({"e1": 5.0, "e2": 3.0}, params) == ("e1", False)
    assert assign({"e1": 2.0, "e2": 1.0}, params) == (None, False)


def test_run_linking_stage_is_idempotent_and_every_complaint_in_at_most_one_cohort():
    pipeline_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "dev-run-2"
    config = PipelineConfig.load()
    session_factory = make_session_factory(pipeline_url)

    try:
        run_clustering_stage(session_factory, run_id, config.clustering)

        first = run_linking_stage(session_factory, run_id, config.linking)
        second = run_linking_stage(session_factory, run_id, config.linking)
        assert first == second

        with get_session(pipeline_url) as session:
            n_members = session.execute(
                text("SELECT count(*) FROM app.cohort_members WHERE run_id = :rid"), {"rid": run_id}
            ).scalar_one()
            n_distinct = session.execute(
                text("SELECT count(DISTINCT complaint_id) FROM app.cohort_members WHERE run_id = :rid"), {"rid": run_id}
            ).scalar_one()
            assert n_members == n_distinct

            linked_without_evidence = session.execute(
                text(
                    """
                    SELECT count(*) FROM app.cohorts c
                    WHERE c.run_id = :rid AND c.kind = 'linked'
                    AND NOT EXISTS (SELECT 1 FROM app.cohort_event_links l WHERE l.cohort_id = c.id)
                    """
                ),
                {"rid": run_id},
            ).scalar_one()
            assert linked_without_evidence == 0
    finally:
        with get_session(pipeline_url) as session:
            session.execute(text("DELETE FROM app.cohort_members WHERE run_id = :rid"), {"rid": run_id})
            session.execute(text("DELETE FROM app.cohort_event_links WHERE run_id = :rid"), {"rid": run_id})
            session.execute(text("DELETE FROM app.cohorts WHERE run_id = :rid"), {"rid": run_id})
            session.execute(text("DELETE FROM app.symptom_cluster_members WHERE run_id = :rid"), {"rid": run_id})
            session.execute(text("DELETE FROM app.symptom_clusters WHERE run_id = :rid"), {"rid": run_id})
            session.commit()
