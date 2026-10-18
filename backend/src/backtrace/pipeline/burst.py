"""Complaint burst detection (§8.2 step 5): fixed-size per-region time
buckets (empty buckets count as 0), flagged against a rolling baseline of
the previous baseline_buckets bins."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Complaint, ComplaintBurst, ComplaintFeatures
from backtrace.llm.config import BurstParams


@dataclass(frozen=True)
class Burst:
    region: str
    start_at: datetime
    end_at: datetime
    complaint_count: int
    peak_score: float


def _bucket_index(t: datetime, window_start: datetime, bucket_minutes: int, n_buckets: int) -> int:
    idx = int((t - window_start).total_seconds() // (bucket_minutes * 60))
    return min(max(idx, 0), n_buckets - 1)


def _z(mean: float, std: float, value: float) -> float:
    if std < 1e-9:
        return 0.0 if value == mean else math.inf
    return (value - mean) / std


def detect_bursts(
    received_at_by_region: Mapping[str, Sequence[datetime]],
    *,
    window_start: datetime,
    window_end: datetime,
    params: BurstParams,
) -> list[Burst]:
    span_minutes = (window_end - window_start).total_seconds() / 60
    n_buckets = max(1, math.ceil(span_minutes / params.bucket_minutes))
    bucket_edges = [window_start + timedelta(minutes=i * params.bucket_minutes) for i in range(n_buckets + 1)]

    bursts: list[Burst] = []
    for region, timestamps in received_at_by_region.items():
        counts = np.zeros(n_buckets, dtype=float)
        for t in timestamps:
            counts[_bucket_index(t, window_start, params.bucket_minutes, n_buckets)] += 1

        scores = np.zeros(n_buckets, dtype=float)
        flagged = np.zeros(n_buckets, dtype=bool)
        # Baseline history excludes already-flagged bins, so a sustained
        # burst is scored against the pre-burst baseline for its whole
        # duration instead of the second bin comparing itself to the first.
        history: list[float] = []
        for i in range(n_buckets):
            if len(history) >= params.baseline_buckets:
                baseline = np.array(history[-params.baseline_buckets :])
                score = _z(baseline.mean(), baseline.std(), counts[i])
                scores[i] = score
                flagged[i] = counts[i] >= params.min_count and score >= params.z_threshold
            if not flagged[i]:
                history.append(counts[i])

        i = 0
        while i < n_buckets:
            if not flagged[i]:
                i += 1
                continue
            start = i
            while i < n_buckets and flagged[i]:
                i += 1
            end = i - 1
            bursts.append(
                Burst(
                    region=region,
                    start_at=bucket_edges[start],
                    end_at=bucket_edges[end + 1],
                    complaint_count=int(counts[start : end + 1].sum()),
                    peak_score=float(scores[start : end + 1].max()),
                )
            )
    return bursts


def run_burst_stage(session_factory: sessionmaker, run_id: str, params: BurstParams) -> dict:
    """Region-only (node-level bursts are YAGNI until event scopes carry a
    node — §8.2 step 5). Window = the span of the run's own in-scope
    complaints (those with features under run_id)."""
    with session_factory() as session:
        rows = session.execute(
            select(Complaint.region, Complaint.received_at)
            .join(ComplaintFeatures, ComplaintFeatures.complaint_id == Complaint.complaint_id)
            .where(ComplaintFeatures.run_id == run_id)
        ).all()

        if not rows:
            return {"bursts": 0}

        received_at_by_region: dict[str, list[datetime]] = {}
        for region, received_at in rows:
            received_at_by_region.setdefault(region, []).append(received_at)

        window_start = min(received_at for _, received_at in rows)
        window_end = max(received_at for _, received_at in rows)
        bursts = detect_bursts(received_at_by_region, window_start=window_start, window_end=window_end, params=params)

        session.execute(delete(ComplaintBurst).where(ComplaintBurst.run_id == run_id))
        for n, burst in enumerate(bursts):
            session.add(
                ComplaintBurst(
                    id=f"burst-{run_id}-{n}",
                    run_id=run_id,
                    region=burst.region,
                    start_at=burst.start_at,
                    end_at=burst.end_at,
                    complaint_count=burst.complaint_count,
                    peak_score=burst.peak_score,
                )
            )
        session.commit()

    return {"bursts": len(bursts)}
