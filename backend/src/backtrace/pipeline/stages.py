"""Idempotent, resumable extraction/embedding stages (§8.2 steps 1-3, §11
Phase 4). Each stage reads only app.complaints and writes its own per-run
table keyed by (run_id, complaint_id), so a rerun or resume never
duplicates work and a needs_review complaint is not retried forever."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Complaint, ComplaintEmbedding, ComplaintFeatures
from backtrace.llm.providers import EmbeddingProvider, ExtractionProvider
from backtrace.pipeline.extract import embed_complaint, extract_complaint


def _pending_extraction_ids(session_factory: sessionmaker, run_id: str) -> list[str]:
    with session_factory() as session:
        done = {row[0] for row in session.execute(select(ComplaintFeatures.complaint_id).where(ComplaintFeatures.run_id == run_id))}
        return [row[0] for row in session.execute(select(Complaint.complaint_id)) if row[0] not in done]


def _extract_one(session_factory: sessionmaker, run_id: str, complaint_id: str, provider: ExtractionProvider, cache_only: bool) -> str:
    with session_factory() as session:
        complaint = session.get(Complaint, complaint_id)
        outcome = extract_complaint(session, run_id, complaint.text, provider, cache_only=cache_only)
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
    session_factory: sessionmaker, run_id: str, provider: ExtractionProvider, max_concurrent_calls: int, cache_only: bool = False
) -> dict:
    pending = _pending_extraction_ids(session_factory, run_id)
    with ThreadPoolExecutor(max_workers=max(1, max_concurrent_calls)) as pool:
        futures = [pool.submit(_extract_one, session_factory, run_id, cid, provider, cache_only) for cid in pending]
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


def _embed_one(session_factory: sessionmaker, run_id: str, complaint_id: str, provider: EmbeddingProvider, cache_only: bool) -> str:
    with session_factory() as session:
        features = session.get(ComplaintFeatures, (run_id, complaint_id))
        symptom_summary = " ".join(features.extraction.get("symptoms", []))
        result = embed_complaint(session, run_id, features.pii_redacted_text, symptom_summary, provider, cache_only=cache_only)
        session.merge(
            ComplaintEmbedding(run_id=run_id, complaint_id=complaint_id, model_version=result.model_version, embedding=result.vector)
        )
        session.commit()
    return complaint_id


def run_embedding_stage(
    session_factory: sessionmaker, run_id: str, provider: EmbeddingProvider, max_concurrent_calls: int, cache_only: bool = False
) -> dict:
    pending = _pending_embedding_ids(session_factory, run_id)
    with ThreadPoolExecutor(max_workers=max(1, max_concurrent_calls)) as pool:
        futures = [pool.submit(_embed_one, session_factory, run_id, cid, provider, cache_only) for cid in pending]
        for future in as_completed(futures):
            future.result()
    return {"pending_at_start": len(pending), "processed": len(pending)}
