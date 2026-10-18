import datetime as dt
import os

from backtrace.db.models import LlmCache, LlmCall, PipelineRun
from backtrace.db.session import get_session
from backtrace.llm.providers import EmbeddingResult, ExtractionResult, FakeEmbeddingProvider, FakeExtractionProvider
from backtrace.pipeline.extract import embed_complaint, extract_complaint


class _CountingExtractionProvider(FakeExtractionProvider):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, text: str) -> ExtractionResult:
        self.calls += 1
        self.last_input = text
        return super().extract(text)


class _AlwaysInvalidProvider:
    model_id = "always-invalid-v1"
    prompt_version = "extraction-v1"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, text: str) -> ExtractionResult:
        self.calls += 1
        return ExtractionResult(raw_json="{not valid json", tokens_in=1, tokens_out=1)


class _CountingEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(dimension=8)
        self.calls = 0

    def embed(self, text: str) -> EmbeddingResult:
        self.calls += 1
        return super().embed(text)


def _cleanup(session, run_id: str, cache_keys: list[str]) -> None:
    session.query(LlmCall).filter(LlmCall.run_id == run_id).delete()
    for key in cache_keys:
        row = session.get(LlmCache, key)
        if row is not None:
            session.delete(row)
    run = session.get(PipelineRun, run_id)
    if run is not None:
        session.delete(run)
    session.commit()


def test_extraction_cache_hit_skips_the_provider():
    run_id = "test-run-extract-cache"
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    provider = _CountingExtractionProvider()
    with get_session(database_url) as session:
        session.add(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()

        text = "My fiber_pro connection keeps dropping in north."
        first = extract_complaint(session, run_id, text, provider)
        session.commit()
        second = extract_complaint(session, run_id, text, provider)
        session.commit()

        assert provider.calls == 1  # second call was a cache hit
        assert first.extraction == second.extraction
        assert not first.needs_review

        from backtrace.llm.cache import cache_key

        _cleanup(session, run_id, [cache_key(provider.model_id, provider.prompt_version, text)])


def test_extraction_invalid_response_retries_once_then_needs_review():
    run_id = "test-run-extract-invalid"
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    provider = _AlwaysInvalidProvider()
    with get_session(database_url) as session:
        session.add(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()

        outcome = extract_complaint(session, run_id, "some complaint text", provider)
        session.commit()

        assert outcome.needs_review
        assert outcome.extraction is None
        assert provider.calls == 2  # one try + one retry, no more

        _cleanup(session, run_id, [])


def test_redaction_happens_before_the_provider_sees_the_text():
    run_id = "test-run-extract-redact"
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    provider = _CountingExtractionProvider()
    with get_session(database_url) as session:
        session.add(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()

        text = "Jordan Alvarez, reachable at 555-123-4567, has no service."
        outcome = extract_complaint(session, run_id, text, provider, customer_names=("Jordan Alvarez",))
        session.commit()

        assert "Jordan Alvarez" not in provider.last_input
        assert "555-123-4567" not in provider.last_input
        assert outcome.pii_redacted_text == provider.last_input

        from backtrace.llm.cache import cache_key

        _cleanup(session, run_id, [cache_key(provider.model_id, provider.prompt_version, outcome.pii_redacted_text)])


def test_embedding_cache_hit_skips_the_provider():
    run_id = "test-run-embed-cache"
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    provider = _CountingEmbeddingProvider()
    with get_session(database_url) as session:
        session.add(PipelineRun(run_id=run_id, dataset_profile="tiny", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()

        first = embed_complaint(session, run_id, "redacted text", "summary", provider)
        session.commit()
        second = embed_complaint(session, run_id, "redacted text", "summary", provider)
        session.commit()

        assert provider.calls == 1
        assert first.vector == second.vector
        assert len(first.vector) == 8

        from backtrace.llm.cache import cache_key

        key = cache_key(provider.model_id, provider.prompt_version, "redacted text\n\nsummary", dimension=8)
        _cleanup(session, run_id, [key])
