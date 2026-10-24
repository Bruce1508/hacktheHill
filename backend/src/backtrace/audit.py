"""Append-only audit log with a hash chain (§7.1, §12): each row hashes the
previous row's hash plus its own fields, so tampering with any row breaks
every hash after it."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backtrace.db.models import AuditLog


def _last_hash(session: Session) -> str | None:
    row = session.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    return row


def append_audit(
    session: Session,
    actor_user_id: str,
    role: str,
    auth_mode: str,
    action: str,
    target_type: str,
    target_id: str,
    before: dict,
    after: dict,
) -> AuditLog:
    prev_hash = _last_hash(session)
    payload = {
        "prev_hash": prev_hash, "actor_user_id": actor_user_id, "role": role, "auth_mode": auth_mode,
        "action": action, "target_type": target_type, "target_id": target_id, "before": before, "after": after,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    row = AuditLog(
        actor_user_id=actor_user_id, role=role, auth_mode=auth_mode, action=action,
        target_type=target_type, target_id=target_id, before=before, after=after,
        prev_hash=prev_hash, hash=digest,
    )
    session.add(row)
    session.flush()
    return row
