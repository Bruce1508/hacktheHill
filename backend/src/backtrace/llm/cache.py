"""Persistent llm_cache (§8.5): a rerun over the same input, model, and
prompt_version must cost zero tokens."""

import hashlib
import json

from sqlalchemy.orm import Session

from backtrace.db.models import LlmCache


def cache_key(model: str, prompt_version: str, input_text: str, **extra: object) -> str:
    """Hash of everything that affects the output. `extra` carries fields
    like embedding task_type/dimension so a dimension change is a cache miss."""
    payload = {"model": model, "prompt_version": prompt_version, "input": input_text, **extra}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def get_cached(session: Session, key: str) -> dict | None:
    row = session.get(LlmCache, key)
    return row.response if row else None


def put_cached(session: Session, key: str, response: dict) -> None:
    session.merge(LlmCache(key=key, response=response))
