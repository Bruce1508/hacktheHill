import hashlib
import json

from backtrace.audit import append_audit
from backtrace.db.models import AuditLog
from backtrace.db.session import get_session


def test_hash_chains_to_previous_row(database_url_pipeline):
    with get_session(database_url_pipeline) as session:
        session.query(AuditLog).delete()
        session.commit()

        first = append_audit(session, "demo-agent", "agent", "dev", "cohort.view", "cohort", "c1", before={}, after={})
        second = append_audit(session, "demo-team-lead", "team_lead", "dev", "cohort.confirm", "cohort", "c1", before={"status": "proposed"}, after={"status": "confirmed"})

        assert first.prev_hash is None
        assert second.prev_hash == first.hash
        expected = hashlib.sha256(
            json.dumps(
                {"prev_hash": first.hash, "actor_user_id": "demo-team-lead", "role": "team_lead", "auth_mode": "dev", "action": "cohort.confirm", "target_type": "cohort", "target_id": "c1", "before": {"status": "proposed"}, "after": {"status": "confirmed"}},
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert second.hash == expected
