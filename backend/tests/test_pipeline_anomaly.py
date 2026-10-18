import datetime as dt
import os

import numpy as np
from sqlalchemy import select, text

from backtrace.db.models import DetectedAnomaly, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.config import AnomalyParams, PipelineConfig
from backtrace.pipeline.anomaly import detect_anomalies, run_anomaly_stage

# dns_failure is excluded: the dev generator deliberately makes it a
# telemetry-silent incident (only latency_ms rises, which isn't in
# anomaly.metrics) — a "weak signal" meant to be caught by other evidence
# in Task 5's linking, not by this stage.
TELEMETRY_VISIBLE_NETWORK_KINDS = {"fiber_cut", "optical_degradation", "maintenance_overrun"}

PARAMS = AnomalyParams(window_points=48, z_threshold=4.0, min_points=2, metrics=("packet_loss_pct", "errored_seconds", "optical_power_dbm"))


def _timestamps(n: int) -> list[dt.datetime]:
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return [start + dt.timedelta(minutes=5 * i) for i in range(n)]


def test_a_sustained_spike_is_detected_as_one_anomaly():
    n = 200
    values = np.ones(n)
    values[120:130] = 50.0  # 10-point spike at index 120..129
    anomalies = detect_anomalies(_timestamps(n), values, series_key=("node-1", None), metric="packet_loss_pct", params=PARAMS)

    assert len(anomalies) == 1
    ts = _timestamps(n)
    assert anomalies[0].start_at == ts[120]
    assert anomalies[0].end_at == ts[129]


def test_a_one_point_spike_is_dropped_below_min_points():
    n = 200
    values = np.ones(n)
    values[120] = 50.0
    params = AnomalyParams(window_points=48, z_threshold=4.0, min_points=2, metrics=PARAMS.metrics)
    anomalies = detect_anomalies(_timestamps(n), values, series_key=("node-1", None), metric="packet_loss_pct", params=params)

    assert anomalies == []


def test_optical_power_drop_is_detected_but_a_rise_is_not():
    n = 200
    dropping = np.full(n, -20.0)
    dropping[120:130] = -30.0
    anomalies = detect_anomalies(_timestamps(n), dropping, series_key=("node-1", None), metric="optical_power_dbm", params=PARAMS)
    assert len(anomalies) == 1

    rising = np.full(n, -20.0)
    rising[120:130] = -10.0
    anomalies = detect_anomalies(_timestamps(n), rising, series_key=("node-1", None), metric="optical_power_dbm", params=PARAMS)
    assert anomalies == []


def test_a_flat_series_has_no_anomalies():
    n = 200
    values = np.full(n, 7.0)
    anomalies = detect_anomalies(_timestamps(n), values, series_key=("node-1", None), metric="packet_loss_pct", params=PARAMS)
    assert anomalies == []


def test_run_anomaly_stage_is_idempotent_and_overlaps_dev_gold_events():
    pipeline_url = os.environ["DATABASE_URL_PIPELINE"]
    eval_url = os.environ["DATABASE_URL_EVAL"]
    run_id = "test-anomaly-stage-dev-run"
    params = PipelineConfig.load().anomaly
    session_factory = make_session_factory(pipeline_url)

    with get_session(pipeline_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()

    try:
        first = run_anomaly_stage(session_factory, run_id, params)
        second = run_anomaly_stage(session_factory, run_id, params)
        assert first == second
        assert first["anomalies"] > 0

        with get_session(pipeline_url) as session:
            anomalies = session.execute(
                select(DetectedAnomaly.start_at, DetectedAnomaly.end_at).where(DetectedAnomaly.run_id == run_id)
            ).all()

        with get_session(eval_url) as session:
            gold_events = session.execute(text("SELECT start_at, end_at, kind FROM eval.gold_events")).all()

        network_events = [e for e in gold_events if e.kind in TELEMETRY_VISIBLE_NETWORK_KINDS]
        assert network_events  # sanity: the dev fixture has network gold events
        for event in network_events:
            assert any(
                a.start_at <= event.end_at and a.end_at >= event.start_at for a in anomalies
            ), f"no anomaly overlaps gold event window ({event.kind})"
    finally:
        with get_session(pipeline_url) as session:
            session.execute(text("DELETE FROM app.detected_anomalies WHERE run_id = :rid"), {"rid": run_id})
            session.delete(session.get(PipelineRun, run_id))
            session.commit()
