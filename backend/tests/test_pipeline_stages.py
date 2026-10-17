import datetime as dt
import os

import pytest

from backtrace.db.models import Complaint, ComplaintEmbedding, ComplaintFeatures, Customer, LlmCache, LlmCall, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.cache import cache_key
from backtrace.llm.providers import FakeEmbeddingProvider, FakeExtractionProvider
from backtrace.pipeline import stages as stages_module
from backtrace.pipeline.extract import embedding_input_and_key
from backtrace.pipeline.stages import run_embedding_stage, run_extraction_stage

RUN_ID = "test-stages-guard-run-1"
COMPLAINT_ID = "test-stages-guard-complaint-1"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(Customer(id="test-stages-cust-1", region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        session.merge(
            PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc))
        )
        session.merge(
            Complaint(
                complaint_id=COMPLAINT_ID,
                customer_id="test-stages-cust-1",
                received_at=dt.datetime.now(dt.timezone.utc),
                channel="web",
                text="My bill is wrong.",
                product="fiber_basic",
                region="north",
                node_id="node-north-1",
            )
        )
        session.commit()


def _cleanup(database_url: str) -> None:
    with get_session(database_url) as session:
        features = session.get(ComplaintFeatures, (RUN_ID, COMPLAINT_ID))
        if features is not None:
            session.delete(features)
        complaint = session.get(Complaint, COMPLAINT_ID)
        if complaint is not None:
            session.delete(complaint)
        session.commit()
        session.delete(session.get(PipelineRun, RUN_ID))
        session.delete(session.get(Customer, "test-stages-cust-1"))
        session.commit()


def test_run_extraction_stage_refuses_to_exceed_max_calls_per_run():
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    _seed(database_url)
    try:
        session_factory = make_session_factory(database_url)
        with pytest.raises(RuntimeError, match="max_calls_per_run"):
            run_extraction_stage(session_factory, RUN_ID, FakeExtractionProvider(), max_concurrent_calls=4, max_calls_per_run=0)

        with get_session(database_url) as session:
            assert session.get(ComplaintFeatures, (RUN_ID, COMPLAINT_ID)) is None  # guard fired before any provider call
    finally:
        _cleanup(database_url)


class _CountingBatchEmbeddingProvider(FakeEmbeddingProvider):
    """Records the size of every embed_batch call, so tests can assert on
    the chunking without caring about FakeEmbeddingProvider's vectors."""

    def __init__(self) -> None:
        super().__init__(dimension=768)
        self.batch_sizes: list[int] = []

    def embed_batch(self, texts):
        self.batch_sizes.append(len(texts))
        return super().embed_batch(texts)


class _FakeRateLimiter:
    """Records acquire() calls instead of sleeping. Installed in place of
    the real RateLimiter via monkeypatch."""

    instances: list["_FakeRateLimiter"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.acquire_calls = 0
        _FakeRateLimiter.instances.append(self)

    def acquire(self) -> None:
        self.acquire_calls += 1


EMBED_RUN_ID = "test-stages-embed-run-1"
EMBED_RUN_ID_2 = "test-stages-embed-run-2"
EMBED_CUSTOMER_ID = "test-stages-embed-cust-1"
EMBED_COMPLAINT_IDS = [f"test-stages-embed-complaint-{i}" for i in range(7)]


def _seed_embedding_complaints(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(Customer(id=EMBED_CUSTOMER_ID, region="north", plan="fiber_basic", segment="residential", node_id="node-north-1"))
        for complaint_id in EMBED_COMPLAINT_IDS:
            session.merge(
                Complaint(
                    complaint_id=complaint_id,
                    customer_id=EMBED_CUSTOMER_ID,
                    received_at=dt.datetime.now(dt.timezone.utc),
                    channel="web",
                    text=f"Complaint text for {complaint_id}.",
                    product="fiber_basic",
                    region="north",
                    node_id="node-north-1",
                )
            )
        session.commit()


def _seed_embedding_features(database_url: str, run_id: str) -> None:
    """Features for `run_id`, built from text that is IDENTICAL across runs
    so the cache key (which does not include run_id) is identical too."""
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=run_id, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        for complaint_id in EMBED_COMPLAINT_IDS:
            session.merge(
                ComplaintFeatures(
                    run_id=run_id,
                    complaint_id=complaint_id,
                    extraction={"symptoms": [f"symptom-{complaint_id}"]},
                    extraction_version="extraction-v1",
                    pii_redacted_text=f"redacted text for {complaint_id}",
                    needs_review=False,
                )
            )
        session.commit()


def _cleanup_embedding(database_url: str, provider) -> None:
    with get_session(database_url) as session:
        for run_id in (EMBED_RUN_ID, EMBED_RUN_ID_2):
            session.query(LlmCall).filter(LlmCall.run_id == run_id).delete()
            for complaint_id in EMBED_COMPLAINT_IDS:
                embedding = session.get(ComplaintEmbedding, (run_id, complaint_id))
                if embedding is not None:
                    session.delete(embedding)
                features = session.get(ComplaintFeatures, (run_id, complaint_id))
                if features is not None:
                    session.delete(features)
            session.commit()
            run = session.get(PipelineRun, run_id)
            if run is not None:
                session.delete(run)
        for complaint_id in EMBED_COMPLAINT_IDS:
            key = cache_key(provider.model_id, provider.prompt_version, f"redacted text for {complaint_id}\n\nsymptom-{complaint_id}", dimension=provider.dimension)
            row = session.get(LlmCache, key)
            if row is not None:
                session.delete(row)
            complaint = session.get(Complaint, complaint_id)
            if complaint is not None:
                session.delete(complaint)
        session.commit()
        session.delete(session.get(Customer, EMBED_CUSTOMER_ID))
        session.commit()


def test_run_embedding_stage_batches_caches_and_counts_requests(monkeypatch):
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    provider = _CountingBatchEmbeddingProvider()
    monkeypatch.setattr(stages_module, "RateLimiter", _FakeRateLimiter)
    _FakeRateLimiter.instances.clear()
    _seed_embedding_complaints(database_url)
    _seed_embedding_features(database_url, EMBED_RUN_ID)
    try:
        session_factory = make_session_factory(database_url)

        result = run_embedding_stage(session_factory, EMBED_RUN_ID, provider, max_calls_per_run=100, batch_size=3, max_calls_per_minute=60)

        assert provider.batch_sizes == [3, 3, 1]
        assert result == {"pending_at_start": 7, "processed": 7, "requests": 3}
        assert len(_FakeRateLimiter.instances) == 1
        assert _FakeRateLimiter.instances[0].acquire_calls == 3  # once per chunk, not once per item

        with get_session(database_url) as session:
            embeddings = [session.get(ComplaintEmbedding, (EMBED_RUN_ID, cid)) for cid in EMBED_COMPLAINT_IDS]
            assert all(e is not None for e in embeddings)
            calls = session.query(LlmCall).filter(LlmCall.run_id == EMBED_RUN_ID, LlmCall.stage == "embedding").all()
            assert len(calls) == 7
            assert all(not c.cache_hit for c in calls)

        # Rerun under a NEW run_id, cache_only=True: the shared llm_cache
        # rows from the first run must satisfy every lookup with zero
        # provider calls.
        _seed_embedding_features(database_url, EMBED_RUN_ID_2)
        result2 = run_embedding_stage(session_factory, EMBED_RUN_ID_2, provider, max_calls_per_run=100, batch_size=3, cache_only=True)

        assert provider.batch_sizes == [3, 3, 1]  # unchanged: no new provider calls
        assert result2["requests"] == 0

        with get_session(database_url) as session:
            calls2 = session.query(LlmCall).filter(LlmCall.run_id == EMBED_RUN_ID_2, LlmCall.stage == "embedding").all()
            assert len(calls2) == 7
            assert all(c.cache_hit for c in calls2)
            embeddings2 = [session.get(ComplaintEmbedding, (EMBED_RUN_ID_2, cid)) for cid in EMBED_COMPLAINT_IDS]
            assert all(e is not None for e in embeddings2)
    finally:
        _cleanup_embedding(database_url, provider)


def test_embedding_cache_key_matches_embed_complaint_for_same_input():
    provider = FakeEmbeddingProvider(dimension=8)
    redacted_text = "redacted text"
    symptom_summary = "summary"

    input_text, key = embedding_input_and_key(provider, redacted_text, symptom_summary)

    assert input_text == f"{redacted_text}\n\n{symptom_summary}"
    assert key == cache_key(provider.model_id, provider.prompt_version, input_text, dimension=provider.dimension)
