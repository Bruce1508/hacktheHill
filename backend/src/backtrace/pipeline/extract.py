"""Orchestrates redaction -> cache -> provider -> validation for a single
complaint's extraction and embedding (§8.2 steps 1-3). The worker (Phase 4)
calls these per complaint under an existing app.pipeline_runs row."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backtrace.contracts.extraction import ComplaintExtraction
from backtrace.db.models import LlmCall
from backtrace.llm.cache import cache_key, get_cached, put_cached
from backtrace.llm.providers import EmbeddingProvider, ExtractionProvider
from backtrace.pipeline.redact import redact_text


class _Identifiable(Protocol):
    model_id: str
    prompt_version: str


def _log_call(
    session: Session,
    run_id: str,
    stage: str,
    provider: _Identifiable,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
    cache_hit: bool,
) -> None:
    session.add(
        LlmCall(
            run_id=run_id,
            stage=stage,
            model=provider.model_id,
            prompt_version=provider.prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            # ponytail: no per-model pricing table yet; add real $ when cost
            # dashboards matter. Cached calls are genuinely free either way.
            cost_estimate=Decimal("0"),
            cache_hit=cache_hit,
            called_at=dt.datetime.now(dt.timezone.utc),
        )
    )


@dataclass(frozen=True)
class ExtractionOutcome:
    pii_redacted_text: str
    extraction: ComplaintExtraction | None  # None means needs_review
    extraction_version: str
    needs_review: bool


def extract_complaint(
    session: Session,
    run_id: str,
    text: str,
    provider: ExtractionProvider,
    customer_names: tuple[str, ...] = (),
    cache_only: bool = False,
) -> ExtractionOutcome:
    """Cache stores only validated extractions, so a cache hit never needs
    re-validation and a bad response never sticks in the cache."""
    redacted = redact_text(text, customer_names)
    key = cache_key(provider.model_id, provider.prompt_version, redacted)

    cached = get_cached(session, key)
    if cached is not None:
        _log_call(session, run_id, "extraction", provider, 0, 0, 0.0, cache_hit=True)
        session.commit()
        return ExtractionOutcome(redacted, ComplaintExtraction.model_validate(cached["extraction"]), provider.prompt_version, needs_review=False)
    session.commit()  # release the connection before the slow network call
    if cache_only:
        raise RuntimeError(f"cache_only mode: no cached extraction for key {key}")

    for _ in range(2):  # one retry on schema-validation failure
        started = time.monotonic()
        result = provider.extract(redacted)  # no open transaction during this call
        latency_ms = (time.monotonic() - started) * 1000
        _log_call(session, run_id, "extraction", provider, result.tokens_in, result.tokens_out, latency_ms, cache_hit=False)
        try:
            parsed = ComplaintExtraction.model_validate_json(result.raw_json)
        except ValidationError:
            session.commit()  # persist the call log; release before the retry's call
            continue
        put_cached(session, key, {"extraction": parsed.model_dump()})
        session.commit()
        return ExtractionOutcome(redacted, parsed, provider.prompt_version, needs_review=False)

    return ExtractionOutcome(redacted, None, provider.prompt_version, needs_review=True)


@dataclass(frozen=True)
class EmbeddingOutcome:
    vector: list[float]
    model_version: str


def embed_complaint(
    session: Session,
    run_id: str,
    redacted_text: str,
    symptom_summary: str,
    provider: EmbeddingProvider,
    cache_only: bool = False,
) -> EmbeddingOutcome:
    """Embeds redacted text + validated symptom summary only (§8.2 step 3) —
    never the raw, un-redacted complaint."""
    input_text = f"{redacted_text}\n\n{symptom_summary}"
    key = cache_key(provider.model_id, provider.prompt_version, input_text, dimension=provider.dimension)

    cached = get_cached(session, key)
    if cached is not None:
        _log_call(session, run_id, "embedding", provider, 0, 0, 0.0, cache_hit=True)
        session.commit()
        return EmbeddingOutcome(cached["vector"], provider.model_id)
    session.commit()  # release the connection before the slow network call
    if cache_only:
        raise RuntimeError(f"cache_only mode: no cached embedding for key {key}")

    started = time.monotonic()
    result = provider.embed(input_text)  # no open transaction during this call
    latency_ms = (time.monotonic() - started) * 1000
    _log_call(session, run_id, "embedding", provider, result.billable_units, 0, latency_ms, cache_hit=False)
    put_cached(session, key, {"vector": result.vector})
    session.commit()
    return EmbeddingOutcome(result.vector, provider.model_id)
