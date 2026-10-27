import hashlib
import json

from backtrace.audit import _last_hash, append_audit
from backtrace.db.models import AuditLog
from backtrace.db.session import get_session


def test_hash_chains_to_previous_row(database_url_pipeline):
    # Never wipes app.audit_log (it's shared, live state): chains onto
    # whatever tail already exists and deletes only the two rows it adds.
    ids: list[int] = []
    with get_session(database_url_pipeline) as session:
        try:
            prior_tail = _last_hash(session)
            first = append_audit(session, "demo-agent", "agent", "dev", "cohort.view", "cohort", "test-audit-c1", before={}, after={})
            second = append_audit(session, "demo-team-lead", "team_lead", "dev", "cohort.confirm", "cohort", "test-audit-c1", before={"status": "proposed"}, after={"status": "confirmed"})
            ids = [first.id, second.id]
            session.commit()

            assert first.prev_hash == prior_tail
            assert second.prev_hash == first.hash
            expected = hashlib.sha256(
                json.dumps(
                    {"prev_hash": first.hash, "actor_user_id": "demo-team-lead", "role": "team_lead", "auth_mode": "dev", "action": "cohort.confirm", "target_type": "cohort", "target_id": "test-audit-c1", "before": {"status": "proposed"}, "after": {"status": "confirmed"}},
                    sort_keys=True, separators=(",", ":"),
                ).encode()
            ).hexdigest()
            assert second.hash == expected
        finally:
            session.rollback()
            session.query(AuditLog).filter(AuditLog.id.in_(ids)).delete()
            session.commit()
