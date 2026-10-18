"""Telemetry anomaly detection (§8.2 step 4): rolling z-score over the
previous window of samples per (node_id, link_id) series."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import DetectedAnomaly, Telemetry
from backtrace.llm.config import AnomalyParams
from backtrace.pipeline._zscore import zscore


@dataclass(frozen=True)
class Anomaly:
    series_key: tuple[str | None, str | None]  # (node_id, link_id)
    metric: str
    start_at: datetime
    end_at: datetime
    peak_score: float


def _score(window: np.ndarray, value: float, metric: str) -> float:
    mean_prev = window.mean()
    std_prev = window.std()
    raw_z = zscore(mean_prev, std_prev, value)
    # optical_power_dbm: a drop is the failure mode, not a rise — flip the
    # sign so dropping power scores positive and rising power never fires.
    return -raw_z if metric == "optical_power_dbm" else raw_z


def detect_anomalies(
    timestamps: Sequence[datetime],
    values: np.ndarray,
    *,
    series_key: tuple[str | None, str | None],
    metric: str,
    params: AnomalyParams,
) -> list[Anomaly]:
    values = np.asarray(values, dtype=float)
    n = len(values)
    scores = np.zeros(n, dtype=float)
    flagged = np.zeros(n, dtype=bool)
    # Baseline history excludes already-flagged points, so a sustained
    # anomaly is scored against the pre-anomaly baseline for its whole
    # duration instead of drifting toward the anomaly itself.
    history: deque[float] = deque(maxlen=params.window_points)
    for i in range(n):
        if len(history) >= params.window_points:
            window = np.array(history)
            score = _score(window, values[i], metric)
            scores[i] = score
            flagged[i] = score >= params.z_threshold
        if not flagged[i]:
            history.append(values[i])

    anomalies: list[Anomaly] = []
    i = 0
    while i < n:
        if not flagged[i]:
            i += 1
            continue
        start = i
        while i < n and flagged[i]:
            i += 1
        end = i - 1
        if end - start + 1 >= params.min_points:
            anomalies.append(
                Anomaly(
                    series_key=series_key,
                    metric=metric,
                    start_at=timestamps[start],
                    end_at=timestamps[end],
                    peak_score=float(scores[start : end + 1].max()),
                )
            )
    return anomalies


def run_anomaly_stage(session_factory: sessionmaker, run_id: str, params: AnomalyParams) -> dict:
    """Telemetry is not run-scoped (§8.2 step 4), so this reads all of
    app.telemetry and writes anomalies under run_id. Re-running for the
    same run_id replaces that run's anomalies, so repeated runs on
    unchanged telemetry are idempotent (same row count)."""
    metric_columns = (Telemetry.packet_loss_pct, Telemetry.errored_seconds, Telemetry.optical_power_dbm)
    metric_index = {col.name: i + 1 for i, col in enumerate(metric_columns)}  # +1: series rows start with sampled_at

    with session_factory() as session:
        rows = session.execute(
            select(Telemetry.node_id, Telemetry.link_id, Telemetry.sampled_at, *metric_columns)
            .order_by(Telemetry.node_id, Telemetry.link_id, Telemetry.sampled_at)
        ).all()

        series: dict[tuple[str | None, str | None], list[tuple]] = defaultdict(list)
        for node_id, link_id, sampled_at, packet_loss_pct, errored_seconds, optical_power_dbm in rows:
            series[(node_id, link_id)].append((sampled_at, packet_loss_pct, errored_seconds, optical_power_dbm))

        anomalies: list[Anomaly] = []
        for series_key, samples in series.items():
            timestamps = [row[0] for row in samples]
            for metric in params.metrics:
                idx = metric_index[metric]
                values = np.array([row[idx] for row in samples], dtype=float)
                anomalies.extend(detect_anomalies(timestamps, values, series_key=series_key, metric=metric, params=params))

        session.execute(delete(DetectedAnomaly).where(DetectedAnomaly.run_id == run_id))
        for n, anomaly in enumerate(anomalies):
            session.add(
                DetectedAnomaly(
                    id=f"anom-{run_id}-{n}",
                    run_id=run_id,
                    node_id=anomaly.series_key[0],
                    link_id=anomaly.series_key[1],
                    metric=anomaly.metric,
                    start_at=anomaly.start_at,
                    end_at=anomaly.end_at,
                    peak_score=anomaly.peak_score,
                    method="rolling_z_v1",
                )
            )
        session.commit()

    return {"anomalies": len(anomalies)}
