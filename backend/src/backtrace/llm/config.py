"""Loads configs/pipeline.yaml — model/prompt pins, budget, concurrency
(§6.3, §8.5, §20). Changing a model_id or prompt_version here is an
intentional cache miss."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

# parents[4] from backend/src/backtrace/llm/config.py is the repo root —
# true for a local checkout, but the Docker image only COPYs backend/src/,
# not the repo-root configs/ directory. PIPELINE_CONFIG_PATH (set in
# docker-compose, pointing at a mounted volume) overrides it there.
DEFAULT_CONFIG_PATH = Path(os.environ.get("PIPELINE_CONFIG_PATH") or Path(__file__).resolve().parents[4] / "configs" / "pipeline.yaml")


@dataclass(frozen=True)
class ModelPin:
    model_id: str
    prompt_version: str


@dataclass(frozen=True)
class EmbeddingPin:
    model_id: str
    output_dimensionality: int
    prompt_version: str


@dataclass(frozen=True)
class AnomalyParams:
    window_points: int
    z_threshold: float
    min_points: int
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class BurstParams:
    bucket_minutes: int
    baseline_buckets: int
    z_threshold: float
    min_count: int


@dataclass(frozen=True)
class ClusterParams:
    pca_dims: int
    min_cluster_size: int
    min_samples: int
    structured_weight: float
    seed: int


@dataclass(frozen=True)
class LinkParams:
    weights: Mapping[str, float]
    threshold: float
    ambiguity_margin: float
    lag_max_minutes: int
    temporal_tau_minutes: float


@dataclass(frozen=True)
class PipelineConfig:
    generation: ModelPin
    extraction: ModelPin
    embedding: EmbeddingPin
    hypothesis: ModelPin
    max_calls_per_run: int
    max_concurrent_calls: int
    max_calls_per_minute: int
    embedding_batch_size: int
    cache_only: bool
    anomaly: AnomalyParams
    burst: BurstParams
    clustering: ClusterParams
    linking: LinkParams

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
        raw = yaml.safe_load(path.read_text())
        return cls(
            generation=ModelPin(**raw["generation"]),
            extraction=ModelPin(**raw["extraction"]),
            embedding=EmbeddingPin(**raw["embedding"]),
            hypothesis=ModelPin(**raw["hypothesis"]),
            max_calls_per_run=int(raw["max_calls_per_run"]),
            max_concurrent_calls=int(raw["max_concurrent_calls"]),
            max_calls_per_minute=int(raw["max_calls_per_minute"]),
            embedding_batch_size=int(raw["embedding_batch_size"]),
            cache_only=bool(raw["cache_only"]),
            anomaly=AnomalyParams(
                window_points=int(raw["anomaly"]["window_points"]),
                z_threshold=float(raw["anomaly"]["z_threshold"]),
                min_points=int(raw["anomaly"]["min_points"]),
                metrics=tuple(raw["anomaly"]["metrics"]),
            ),
            burst=BurstParams(
                bucket_minutes=int(raw["burst"]["bucket_minutes"]),
                baseline_buckets=int(raw["burst"]["baseline_buckets"]),
                z_threshold=float(raw["burst"]["z_threshold"]),
                min_count=int(raw["burst"]["min_count"]),
            ),
            clustering=ClusterParams(
                pca_dims=int(raw["clustering"]["pca_dims"]),
                min_cluster_size=int(raw["clustering"]["min_cluster_size"]),
                min_samples=int(raw["clustering"]["min_samples"]),
                structured_weight=float(raw["clustering"]["structured_weight"]),
                seed=int(raw["clustering"]["seed"]),
            ),
            linking=LinkParams(
                weights=dict(raw["linking"]["weights"]),
                threshold=float(raw["linking"]["threshold"]),
                ambiguity_margin=float(raw["linking"]["ambiguity_margin"]),
                lag_max_minutes=int(raw["linking"]["lag_max_minutes"]),
                temporal_tau_minutes=float(raw["linking"]["temporal_tau_minutes"]),
            ),
        )
