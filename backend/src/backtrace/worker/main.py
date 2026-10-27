"""One worker loop (§11): claim/commit a job before slow Gemini work, then
update status in a separate transaction. No broker, no multi-process
parallelism — bounded in-process concurrency happens inside each stage."""

from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time

from backtrace.db import jobs
from backtrace.db.models import Job, WorkerHeartbeat
from backtrace.db.session import make_session_factory
from backtrace.llm.config import PipelineConfig
from backtrace.llm.providers import FakeEmbeddingProvider, FakeExtractionProvider, GeminiEmbeddingProvider, GeminiExtractionProvider, GeminiHypothesisProvider
from backtrace.pipeline.anomaly import run_anomaly_stage
from backtrace.pipeline.burst import run_burst_stage
from backtrace.pipeline.clustering import run_clustering_stage
from backtrace.pipeline.hypothesis import FakeHypothesisProvider, run_hypothesis_stage
from backtrace.pipeline.layout import run_layout_stage
from backtrace.pipeline.linking import run_linking_stage
from backtrace.pipeline.stages import run_embedding_stage, run_extraction_stage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backtrace.worker")

POLL_INTERVAL_SECONDS = 2
HEARTBEAT_INTERVAL_SECONDS = 10
STALE_CHECK_INTERVAL_SECONDS = 60


def _build_providers(config: PipelineConfig, use_fake: bool):
    if use_fake:
        return (
            FakeExtractionProvider(),
            FakeEmbeddingProvider(dimension=config.embedding.output_dimensionality),
            FakeHypothesisProvider(),
        )
    return (
        GeminiExtractionProvider(config.extraction.model_id, config.extraction.prompt_version),
        GeminiEmbeddingProvider(config.embedding.model_id, config.embedding.prompt_version, config.embedding.output_dimensionality),
        GeminiHypothesisProvider(config.hypothesis.model_id, config.hypothesis.prompt_version),
    )


def _heartbeat(session_factory) -> None:
    with session_factory() as session:
        session.merge(WorkerHeartbeat(id=True, updated_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()


def _heartbeat_and_touch_job(session_factory, job_id: int) -> None:
    with session_factory() as session:
        session.merge(WorkerHeartbeat(id=True, updated_at=dt.datetime.now(dt.timezone.utc)))
        session.commit()
        jobs.touch_running(session, job_id)


def _run_job_with_live_heartbeat(session_factory, config: PipelineConfig, extraction_provider, embedding_provider, hypothesis_provider, job: Job) -> None:
    """A job can run for hours (many Gemini calls). Without this, the outer
    loop's heartbeat/stale-check only run between jobs, so /health reports
    the worker dead and a second worker's recover_stale requeues the still-
    running job onto itself — double processing."""
    stop = threading.Event()

    def keep_alive() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            _heartbeat_and_touch_job(session_factory, job.id)

    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        _run_job(session_factory, config, extraction_provider, embedding_provider, hypothesis_provider, job)
    finally:
        stop.set()
        thread.join()


def _run_job(session_factory, config: PipelineConfig, extraction_provider, embedding_provider, hypothesis_provider, job: Job) -> None:
    stages = ("extraction", "embedding", "anomaly", "burst", "clustering", "linking", "hypothesis", "layout") if job.type == "pipeline.run" else (job.stage,)
    for stage in stages:
        if stage == "extraction":
            result = run_extraction_stage(
                session_factory,
                job.run_id,
                extraction_provider,
                config.max_concurrent_calls,
                config.max_calls_per_run,
                max_calls_per_minute=config.max_calls_per_minute,
                cache_only=config.cache_only,
            )
        elif stage == "embedding":
            result = run_embedding_stage(
                session_factory,
                job.run_id,
                embedding_provider,
                config.max_calls_per_run,
                config.embedding_batch_size,
                max_calls_per_minute=config.max_calls_per_minute,
                cache_only=config.cache_only,
            )
        elif stage == "anomaly":
            result = run_anomaly_stage(session_factory, job.run_id, config.anomaly)
        elif stage == "burst":
            result = run_burst_stage(session_factory, job.run_id, config.burst)
        elif stage == "clustering":
            result = run_clustering_stage(session_factory, job.run_id, config.clustering)
        elif stage == "linking":
            result = run_linking_stage(session_factory, job.run_id, config.linking)
        elif stage == "hypothesis":
            result = run_hypothesis_stage(session_factory, job.run_id, hypothesis_provider)
        elif stage == "layout":
            result = run_layout_stage(session_factory, job.run_id)
        else:
            raise ValueError(f"unknown stage {stage!r}")
        logger.info("job=%s run=%s stage=%s result=%s", job.id, job.run_id, stage, result)


def run_forever(database_url: str, use_fake_providers: bool = False) -> None:
    session_factory = make_session_factory(database_url)
    config = PipelineConfig.load()
    extraction_provider, embedding_provider, hypothesis_provider = _build_providers(config, use_fake_providers)
    last_heartbeat = 0.0
    last_stale_check = 0.0

    logger.info(
        "worker started: extraction=%s embedding=%s hypothesis=%s cache_only=%s",
        extraction_provider.model_id,
        embedding_provider.model_id,
        hypothesis_provider.model_id,
        config.cache_only,
    )

    while True:
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
            _heartbeat(session_factory)
            last_heartbeat = now
        if now - last_stale_check >= STALE_CHECK_INTERVAL_SECONDS:
            with session_factory() as session:
                recovered = jobs.recover_stale(session)
                if recovered:
                    logger.warning("recovered %d stale job(s)", recovered)
            last_stale_check = now

        with session_factory() as session:
            job = jobs.claim_next(session)
        if job is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        logger.info("claimed job=%s type=%s run=%s attempt=%d", job.id, job.type, job.run_id, job.attempts)
        try:
            _run_job_with_live_heartbeat(session_factory, config, extraction_provider, embedding_provider, hypothesis_provider, job)
        except Exception as exc:  # noqa: BLE001 — a failed complaint must be visible, not silently dropped
            logger.exception("job=%s failed", job.id)
            with session_factory() as session:
                jobs.mark_failed(session, session.get(Job, job.id), str(exc)[:1000])
        else:
            with session_factory() as session:
                jobs.mark_done(session, session.get(Job, job.id))


def main() -> None:
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    use_fake = os.environ.get("LLM_PROVIDER") == "fake"
    run_forever(database_url, use_fake_providers=use_fake)


if __name__ == "__main__":
    main()
