import datetime as dt
import os

from sqlalchemy import text

from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.config import BurstParams, PipelineConfig
from backtrace.pipeline.burst import detect_bursts, run_burst_stage

WINDOW_START = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
PARAMS = BurstParams(bucket_minutes=15, baseline_buckets=4, z_threshold=3.0, min_count=5)


def _bucket_start(i: int) -> dt.datetime:
    return WINDOW_START + dt.timedelta(minutes=15 * i)


def _steady_and_spike(steady_buckets: int, spike_buckets: int, spike_count: int) -> list[dt.datetime]:
    """1 complaint/bucket for steady_buckets, then spike_count complaints
    spread across each of spike_buckets buckets."""
    timestamps = [_bucket_start(i) for i in range(steady_buckets)]
    for b in range(spike_buckets):
        bucket = steady_buckets + b
        timestamps += [_bucket_start(bucket) + dt.timedelta(minutes=m) for m in range(spike_count)]
    return timestamps


def test_a_sustained_spike_is_detected_as_one_burst():
    timestamps = _steady_and_spike(steady_buckets=10, spike_buckets=2, spike_count=10)
    window_end = _bucket_start(12)

    bursts = detect_bursts({"north": timestamps}, window_start=WINDOW_START, window_end=window_end, params=PARAMS)

    assert len(bursts) == 1
    assert bursts[0].region == "north"
    assert bursts[0].start_at == _bucket_start(10)
    assert bursts[0].end_at == _bucket_start(12)
    assert bursts[0].complaint_count == 20


def test_the_same_complaints_spread_over_two_days_trigger_no_burst():
    n_buckets = 192  # 2 days at 15-min buckets
    window_end = _bucket_start(n_buckets)
    steady = [_bucket_start(i) for i in range(n_buckets)]
    spread_spikes = [_bucket_start(i * (n_buckets // 20)) + dt.timedelta(minutes=1) for i in range(20)]

    bursts = detect_bursts({"north": steady + spread_spikes}, window_start=WINDOW_START, window_end=window_end, params=PARAMS)

    assert bursts == []


def test_a_burst_in_one_region_does_not_appear_in_another():
    timestamps = _steady_and_spike(steady_buckets=10, spike_buckets=2, spike_count=10)
    steady_only = [_bucket_start(i) for i in range(12)]
    window_end = _bucket_start(12)

    bursts = detect_bursts(
        {"north": timestamps, "south": steady_only},
        window_start=WINDOW_START,
        window_end=window_end,
        params=PARAMS,
    )

    assert len(bursts) == 1
    assert bursts[0].region == "north"


def test_a_bucket_below_min_count_is_not_flagged():
    # Flat zero baseline, then one bucket with 4 complaints (min_count=5).
    timestamps = [_bucket_start(10) + dt.timedelta(minutes=m) for m in range(4)]
    window_end = _bucket_start(11)

    bursts = detect_bursts({"north": timestamps}, window_start=WINDOW_START, window_end=window_end, params=PARAMS)

    assert bursts == []


def test_run_burst_stage_is_idempotent():
    pipeline_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "dev-run-2"  # already has complaint_features loaded (dev fixture)
    params = PipelineConfig.load().burst
    session_factory = make_session_factory(pipeline_url)

    try:
        first = run_burst_stage(session_factory, run_id, params)
        second = run_burst_stage(session_factory, run_id, params)
        assert first == second
    finally:
        with get_session(pipeline_url) as session:
            session.execute(text("DELETE FROM app.complaint_bursts WHERE run_id = :rid"), {"rid": run_id})
            session.commit()
