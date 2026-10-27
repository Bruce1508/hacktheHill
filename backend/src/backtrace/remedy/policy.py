"""Deterministic remedy rules (§10.1). Pure Python, no DB, no network —
unit-tested directly. A cohort gets one formula; the amount is computed
per member because outage hours (or overcharge amount) differ per member."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RemedyPolicyFacts:
    id: str
    rule_type: str  # "outage_credit" | "overcharge_refund"
    config: dict
    version: int


@dataclass(frozen=True)
class MemberFacts:
    complaint_id: str
    plan: str
    outage_hours: float | None
    overcharge_amount: Decimal | None
    vulnerability_signals: list[str]


@dataclass(frozen=True)
class RemedyComputation:
    complaint_id: str
    amount: Decimal
    policy_rule_id: str
    policy_version: int
    rationale: str


def apply_policy(policy: RemedyPolicyFacts, member: MemberFacts) -> RemedyComputation | None:
    if member.vulnerability_signals:  # §10.1, §10.3: always individual review
        return None

    if policy.rule_type == "outage_credit":
        if member.outage_hours is None:
            raise ValueError(f"outage_credit policy requires outage_hours for {member.complaint_id}")
        daily_price = Decimal(str(policy.config["price_table"][member.plan]))
        amount = (daily_price * Decimal(str(member.outage_hours)) / Decimal("24")).quantize(Decimal("0.01"))
        rationale = f"Outage credit: {member.outage_hours}h outage at ${daily_price}/day on {member.plan}."
    elif policy.rule_type == "overcharge_refund":
        if member.overcharge_amount is None:
            raise ValueError(f"overcharge_refund policy requires overcharge_amount for {member.complaint_id}")
        goodwill = Decimal(str(policy.config["goodwill_amount"]))
        amount = (member.overcharge_amount + goodwill).quantize(Decimal("0.01"))
        rationale = f"Overcharge refund: ${member.overcharge_amount} refunded plus ${goodwill} goodwill."
    else:
        raise ValueError(f"unknown rule_type {policy.rule_type!r}")

    return RemedyComputation(complaint_id=member.complaint_id, amount=amount, policy_rule_id=policy.id, policy_version=policy.version, rationale=rationale)
