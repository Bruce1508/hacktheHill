"""Loads configs/pipeline.yaml — model/prompt pins, budget, concurrency
(§6.3, §8.5, §20). Changing a model_id or prompt_version here is an
intentional cache miss."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "pipeline.yaml"


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
            cache_only=bool(raw["cache_only"]),
        )
