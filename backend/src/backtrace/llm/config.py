"""Loads configs/pipeline.yaml — model/prompt pins, budget, concurrency
(§6.3, §8.5, §20). Changing a model_id or prompt_version here is an
intentional cache miss."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
class PipelineConfig:
    generation: ModelPin
    extraction: ModelPin
    embedding: EmbeddingPin
    max_calls_per_run: int
    max_concurrent_calls: int
    max_calls_per_minute: int
    cache_only: bool

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> PipelineConfig:
        raw = yaml.safe_load(path.read_text())
        return cls(
            generation=ModelPin(**raw["generation"]),
            extraction=ModelPin(**raw["extraction"]),
            embedding=EmbeddingPin(**raw["embedding"]),
            max_calls_per_run=int(raw["max_calls_per_run"]),
            max_concurrent_calls=int(raw["max_concurrent_calls"]),
            max_calls_per_minute=int(raw["max_calls_per_minute"]),
            cache_only=bool(raw["cache_only"]),
        )
