"""Extraction/embedding provider interface, plus a real Gemini adapter and a
deterministic fake for tests, CI, and cache_only mode (§8.5, §14)."""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from typing import Protocol

from backtrace.contracts.extraction import ComplaintExtraction
from backtrace.llm.prompts import EXTRACTION_PROMPT_V1


@dataclass(frozen=True)
class ExtractionResult:
    raw_json: str
    tokens_in: int
    tokens_out: int


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    # Gemini bills embeddings by input characters, not tokens (§Phase 0 check).
    billable_units: int


class ExtractionProvider(Protocol):
    model_id: str
    prompt_version: str

    def extract(self, text: str) -> ExtractionResult: ...


class EmbeddingProvider(Protocol):
    model_id: str
    prompt_version: str
    dimension: int

    def embed(self, text: str) -> EmbeddingResult: ...


class FakeExtractionProvider:
    """Offline and deterministic: no network call, ever."""

    model_id = "fake-extraction-v1"
    prompt_version = "extraction-v1"

    def extract(self, text: str) -> ExtractionResult:
        payload = ComplaintExtraction(
            product="unknown",
            symptoms=[text[:60]],
            claimed_cause="unspecified",
            issues=[text[:60]],
        )
        return ExtractionResult(raw_json=payload.model_dump_json(), tokens_in=len(text.split()), tokens_out=20)


class FakeEmbeddingProvider:
    """Deterministic pseudo-embedding, seeded by the input text's hash."""

    model_id = "fake-embedding-v1"
    prompt_version = "embedding-v1"

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> EmbeddingResult:
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        return EmbeddingResult(vector=vector, billable_units=len(text))


# Without a timeout a half-closed socket (e.g. after laptop sleep) blocks a
# call forever; observed on 2026-10-03 with the connection stuck in CLOSE_WAIT.
REQUEST_TIMEOUT_MS = 60_000


class GeminiExtractionProvider:
    """Verified live against google-genai 2.25.0 on 2026-09-29 — see
    docs/superpowers/plans/2026-09-28-day2-real-data-language.md. Uses the
    Interactions API; plain generate_content structured output is also
    supported but interactions.create is what the API itself recommends now."""

    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS})

    def extract(self, text: str) -> ExtractionResult:
        prompt = EXTRACTION_PROMPT_V1.format(text=text)
        resp = self._client.interactions.create(
            model=self.model_id,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": ComplaintExtraction.model_json_schema(),
            },
        )
        return ExtractionResult(
            raw_json=resp.output_text,
            tokens_in=resp.usage.total_input_tokens,
            tokens_out=resp.usage.total_output_tokens,
        )


class GeminiEmbeddingProvider:
    """Verified live: embed_content(..., output_dimensionality=768) returns
    exactly 768 values; billable_character_count is Gemini's billing unit
    for embeddings (characters, not tokens)."""

    def __init__(self, model_id: str, prompt_version: str, dimension: int, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self.dimension = dimension
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS})

    def embed(self, text: str) -> EmbeddingResult:
        from google.genai import types

        resp = self._client.models.embed_content(
            model=self.model_id,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimension),
        )
        billable = resp.metadata.billable_character_count if resp.metadata else len(text)
        return EmbeddingResult(vector=list(resp.embeddings[0].values), billable_units=billable)
