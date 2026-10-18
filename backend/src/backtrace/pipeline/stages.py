"""Idempotent, resumable extraction/embedding stages (§8.2 steps 1-3, §11
Phase 4). Each stage reads only app.complaints and writes its own per-run
table keyed by (run_id, complaint_id), so a rerun or resume never
duplicates work and a needs_review complaint is not retried forever."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Complaint, ComplaintEmbedding, ComplaintFeatures
from backtrace.llm.cache import get_cached, put_cached
from backtrace.llm.providers import EmbeddingProvider, ExtractionProvider
from backtrace.llm.rate_limit import RateLimiter
from backtrace.pipeline.extract import _log_call, embedding_input_and_key, extract_complaint


def _pending_extraction_ids(session_factory: sessionmaker, run_id: str) -> list[str]:
    with session_factory() as session:
        done = {row[0] for row in session.execute(select(ComplaintFeatures.complaint_id).where(ComplaintFeatures.run_id == run_id))}
        return [row[0] for row in session.execute(select(Complaint.complaint_id)) if row[0] not in done]


def _extract_one(
    session_factory: sessionmaker, run_id: str, complaint_id: str, provider: ExtractionProvider, cache_only: bool, rate_limiter: RateLimiter | None = None
) -> str:
    with session_factory() as session:
        complaint = session.get(Complaint, complaint_id)
        outcome = extract_complaint(session, run_id, complaint.text, provider, cache_only=cache_only, rate_limiter=rate_limiter)
        session.merge(
            ComplaintFeatures(
                run_id=run_id,
                complaint_id=complaint_id,
                extraction=(outcome.extraction.model_dump() if outcome.extraction else {}),
                extraction_version=outcome.extraction_version,
                pii_redacted_text=outcome.pii_redacted_text,
                needs_review=outcome.needs_review,
            )
        )
        session.commit()
    return complaint_id


def run_extraction_stage(
    session_factory: sessionmaker,
    run_id: str,
    provider: ExtractionProvider,
    max_concurrent_calls: int,
    max_calls_per_run: int,
    max_calls_per_minute: int | None = None,
    cache_only: bool = False,
) -> dict:
    pending = _pending_extraction_ids(session_factory, run_id)
    if len(pending) > max_calls_per_run:
        raise RuntimeError(f"extraction stage would make {len(pending)} calls, exceeding max_calls_per_run={max_calls_per_run}")
    rate_limiter = RateLimiter(max_calls_per_minute) if max_calls_per_minute else None
    with ThreadPoolExecutor(max_workers=max(1, max_concurrent_calls)) as pool:
        futures = [pool.submit(_extract_one, session_factory, run_id, cid, provider, cache_only, rate_limiter) for cid in pending]
        for future in as_completed(futures):
            future.result()  # surface exceptions rather than hiding them
    return {"pending_at_start": len(pending), "processed": len(pending)}


def _pending_embedding_ids(session_factory: sessionmaker, run_id: str) -> list[str]:
    with session_factory() as session:
        ready = {
            row[0]
            for row in session.execute(
                select(ComplaintFeatures.complaint_id).where(
                    ComplaintFeatures.run_id == run_id, ComplaintFeatures.needs_review.is_(False)
                )
            )
        }
        done = {row[0] for row in session.execute(select(ComplaintEmbedding.complaint_id).where(ComplaintEmbedding.run_id == run_id))}
        return sorted(ready - done)


def run_embedding_stage(
    session_factory: sessionmaker,
    run_id: str,
    provider: EmbeddingProvider,
    max_calls_per_run: int,
    batch_size: int,
    max_calls_per_minute: int | None = None,
    cache_only: bool = False,
) -> dict:
    """Batches misses into provider.embed_batch calls of up to `batch_size`
    items (§Day 3 batching: ~1,600 per-complaint requests -> ~16), so the
    Free Tier's per-request quota is spent on requests, not complaints.
    Cache keys are built with embedding_input_and_key, the same helper
    embed_complaint uses, so existing llm_cache rows keep hitting."""
    pending = _pending_embedding_ids(session_factory, run_id)
    if len(pending) > max_calls_per_run:
        # Deliberately conservative: compares complaint count, not the batched
        # request count, against max_calls_per_run.
        raise RuntimeError(f"embedding stage would process {len(pending)} complaints, exceeding max_calls_per_run={max_calls_per_run}")
    rate_limiter = RateLimiter(max_calls_per_minute) if max_calls_per_minute else None

    items: list[tuple[str, str, str]] = []  # (complaint_id, input_text, cache_key)
    with session_factory() as session:
        for complaint_id in pending:
            features = session.get(ComplaintFeatures, (run_id, complaint_id))
            symptom_summary = " ".join(features.extraction.get("symptoms", []))
            input_text, key = embedding_input_and_key(provider, features.pii_redacted_text, symptom_summary)
            items.append((complaint_id, input_text, key))

    misses: list[tuple[str, str, str]] = []
    with session_factory() as session:
        for complaint_id, input_text, key in items:
            cached = get_cached(session, key)
            if cached is None:
                misses.append((complaint_id, input_text, key))
                continue
            _log_call(session, run_id, "embedding", provider, 0, 0, 0.0, cache_hit=True)
            session.merge(ComplaintEmbedding(run_id=run_id, complaint_id=complaint_id, model_version=provider.model_id, embedding=cached["vector"]))
        session.commit()

    if cache_only and misses:
        raise RuntimeError(f"cache_only mode: no cached embedding for {len(misses)} complaint(s)")

    requests = 0
    for start in range(0, len(misses), batch_size):
        chunk = misses[start : start + batch_size]
        texts = [input_text for _, input_text, _ in chunk]
        if rate_limiter is not None:
            rate_limiter.acquire()
        started = time.monotonic()
        results = provider.embed_batch(texts)  # no open transaction during this call
        latency_ms = (time.monotonic() - started) * 1000
        per_item_latency_ms = latency_ms / len(chunk)
        requests += 1
        with session_factory() as session:
            for (complaint_id, _, key), result in zip(chunk, results):
                _log_call(session, run_id, "embedding", provider, result.billable_units, 0, per_item_latency_ms, cache_hit=False)
                put_cached(session, key, {"vector": result.vector})
                session.merge(ComplaintEmbedding(run_id=run_id, complaint_id=complaint_id, model_version=provider.model_id, embedding=result.vector))
            session.commit()  # commit per chunk so progress survives a failure

    return {"pending_at_start": len(pending), "processed": len(pending), "requests": requests}
