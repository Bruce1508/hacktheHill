"""Extraction/embedding provider interface, plus a real Gemini adapter and a
deterministic fake for tests, CI, and cache_only mode (§8.5, §14)."""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from typing import Protocol, Sequence

from backtrace.contracts.extraction import ComplaintExtraction
from backtrace.llm.prompts import DEV_TEXT_PROMPT_V1, EXTRACTION_PROMPT_V1


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
    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]: ...


def split_billable_units(total: int, texts: Sequence[str]) -> list[int]:
    """Splits a batch response's single billable-character total across its
    items, proportionally to each item's length, with the rounding
    remainder on the last item so the parts always sum exactly to `total`."""
    lengths = [len(t) for t in texts]
    total_len = sum(lengths)
    if total_len == 0:
        parts = [0] * len(lengths)
        if parts:
            parts[-1] = total
        return parts
    parts = [total * length // total_len for length in lengths]
    parts[-1] += total - sum(parts)
    return parts


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

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        return [self.embed(t) for t in texts]


# Without a timeout a half-closed socket (e.g. after laptop sleep) blocks a
# call forever; observed on 2026-10-03 with the connection stuck in CLOSE_WAIT.
REQUEST_TIMEOUT_MS = 60_000

# The SDK's default retry policy (5 attempts, backing off up to 60s each) masks
# a day-quota 429 as what looks like an indefinite hang rather than a fast,
# clear error; observed on 2026-10-03. attempts=1 makes a 429/5xx raise immediately.
NO_RETRY = {"attempts": 1}


class GeminiExtractionProvider:
    """Verified live against google-genai 2.25.0 on 2026-09-29 — see
    docs/superpowers/plans/2026-09-28-day2-real-data-language.md. Uses the
    Interactions API; plain generate_content structured output is also
    supported but interactions.create is what the API itself recommends now."""

    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

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
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def embed(self, text: str) -> EmbeddingResult:
        from google.genai import types

        resp = self._client.models.embed_content(
            model=self.model_id,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimension),
        )
        billable = resp.metadata.billable_character_count if resp.metadata else len(text)
        return EmbeddingResult(vector=list(resp.embeddings[0].values), billable_units=billable)

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingResult]:
        """One embed_content call for the whole batch — this is the point of
        batching: ~1,600 per-complaint requests collapse into ~16 (§ Day 3
        plan). Gemini's Free Tier quota is per request, not per item."""
        from google.genai import types

        texts = list(texts)
        resp = self._client.models.embed_content(
            model=self.model_id,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=self.dimension),
        )
        if len(resp.embeddings) != len(texts):
            raise RuntimeError(f"embed_content returned {len(resp.embeddings)} embeddings for {len(texts)} inputs")
        billable_total = resp.metadata.billable_character_count if resp.metadata else None
        units = split_billable_units(billable_total, texts) if billable_total is not None else [len(t) for t in texts]
        return [EmbeddingResult(vector=list(resp.embeddings[i].values), billable_units=units[i]) for i in range(len(texts))]


class GeminiTextProvider:
    """Generates dev-world complaint text via real Gemini. Matches the
    TextProvider protocol in backtrace_eval.generator.dev (realize(seed) ->
    str) by duck typing — not imported here, since backtrace_eval depends on
    backtrace, not the other way round."""

    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def realize(self, seed) -> str:
        # Uses generate_content, not interactions.create: the Interactions API
        # was found on 2026-10-03 to ignore http_options.retry_options and
        # effectively hang on a 429 instead of raising (confirmed live against
        # an exhausted Free Tier quota); generate_content raises immediately.
        prompt = DEV_TEXT_PROMPT_V1.format(
            product=seed.product, region=seed.region, channel=seed.channel, persona=seed.persona,
            symptom=seed.symptom, claimed_cause=seed.claimed_cause or "none stated",
            secondary_symptom=seed.secondary_symptom or "none", is_repeat=seed.is_repeat,
            vulnerability_mentioned=seed.vulnerability_mentioned,
        )
        resp = self._client.models.generate_content(model=self.model_id, contents=prompt)
        return resp.text.strip()


class GeminiHypothesisProvider:
    """Same interactions.create structured-output pattern as
    GeminiExtractionProvider above."""

    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def generate(self, pack):
        from backtrace.contracts.evidence import HypothesisOutput
        from backtrace.llm.prompts import HYPOTHESIS_PROMPT_V1

        prompt = HYPOTHESIS_PROMPT_V1.format(
            complaint_ids=pack.complaint_ids, event_ids=pack.event_ids, anomaly_ids=pack.anomaly_ids,
            score_components=pack.score_components, sample_texts=pack.sample_complaint_texts,
        )
        resp = self._client.interactions.create(
            model=self.model_id, input=prompt,
            response_format={"type": "text", "mime_type": "application/json", "schema": HypothesisOutput.model_json_schema()},
        )
        return HypothesisOutput.model_validate_json(resp.output_text)
