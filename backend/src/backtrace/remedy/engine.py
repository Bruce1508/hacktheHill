"""DB wrapper around the pure policy core (§10.1): computes and persists one
Remedy row per non-vulnerable cohort member; vulnerable members are skipped
and routed to individual review instead. No letter/approval logic here —
Task 7 reads the Remedy rows this writes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, ComplaintFeatures, Customer, DetectedAnomaly, Event, Remedy, RemedyPolicy
from backtrace.remedy.policy import MemberFacts, RemedyPolicyFacts, apply_policy


def _cohort_outage_hours(session, cohort_id: str) -> float | None:
    link = session.execute(
        select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id).order_by(CohortEventLink.overlap_score.desc()).limit(1)
    ).scalar_one_or_none()
    if link is None:
        return None
    if link.anomaly_id:
        anomaly = session.get(DetectedAnomaly, link.anomaly_id)
        return (anomaly.end_at - anomaly.start_at).total_seconds() / 3600
    if link.event_id:
        event = session.get(Event, link.event_id)
        return (event.end_at - event.start_at).total_seconds() / 3600
    return None


def compute_cohort_remedies(session_factory: sessionmaker, cohort_id: str, policy_rule_id: str) -> dict:
    with session_factory() as session:
        cohort = session.get(Cohort, cohort_id)
        policy_row = session.get(RemedyPolicy, policy_rule_id)
        policy = RemedyPolicyFacts(id=policy_row.id, rule_type=policy_row.rule_type, config=policy_row.config, version=policy_row.version)
        outage_hours = _cohort_outage_hours(session, cohort_id) if policy.rule_type == "outage_credit" else None

        session.query(Remedy).filter(Remedy.cohort_id == cohort_id).delete()  # idempotent re-run

        computed = routed = 0
        remedy_ids: list[str] = []
        member_rows = session.execute(select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id)).all()
        for (complaint_id,) in member_rows:
            complaint = session.get(Complaint, complaint_id)
            customer = session.get(Customer, complaint.customer_id)
            features = session.get(ComplaintFeatures, {"run_id": cohort.run_id, "complaint_id": complaint_id})
            vulnerability_signals = features.extraction.get("vulnerability_signals", []) if features else []

            member = MemberFacts(complaint_id=complaint_id, plan=customer.plan, outage_hours=outage_hours, overcharge_amount=None, vulnerability_signals=vulnerability_signals)
            result = apply_policy(policy, member)
            if result is None:
                routed += 1
                continue
            remedy_id = f"{cohort_id}-{complaint_id}"
            session.add(Remedy(id=remedy_id, cohort_id=cohort_id, complaint_id=complaint_id, amount=result.amount, policy_rule_id=result.policy_rule_id, policy_version=result.policy_version, rationale=result.rationale))
            remedy_ids.append(remedy_id)
            computed += 1
        session.commit()
    return {"computed": computed, "routed_to_individual_review": routed, "remedy_ids": remedy_ids}
