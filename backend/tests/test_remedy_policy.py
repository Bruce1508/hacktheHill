from decimal import Decimal

from backtrace.remedy.policy import MemberFacts, RemedyPolicyFacts, apply_policy


def test_outage_credit_proportional_to_daily_price_and_hours():
    policy = RemedyPolicyFacts(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1)
    member = MemberFacts(complaint_id="c1", plan="fiber_pro", outage_hours=12.0, overcharge_amount=None, vulnerability_signals=[])

    result = apply_policy(policy, member)

    assert result.amount == Decimal("1.75")  # 3.50 * 12/24
    assert result.policy_rule_id == "policy-outage-credit-v1"
    assert result.policy_version == 1
    assert "outage" in result.rationale.lower()


def test_overcharge_refund_is_exact_plus_goodwill():
    policy = RemedyPolicyFacts(id="policy-overcharge-refund-v1", rule_type="overcharge_refund", config={"goodwill_amount": 15.00}, version=1)
    member = MemberFacts(complaint_id="c2", plan="tv_bundle", outage_hours=None, overcharge_amount=Decimal("42.00"), vulnerability_signals=[])

    result = apply_policy(policy, member)

    assert result.amount == Decimal("57.00")


def test_vulnerable_member_is_routed_to_individual_review_not_computed():
    policy = RemedyPolicyFacts(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1)
    member = MemberFacts(complaint_id="c3", plan="fiber_pro", outage_hours=12.0, overcharge_amount=None, vulnerability_signals=["mentions hardship"])

    result = apply_policy(policy, member)

    assert result is None  # §10.1: vulnerable -> never an automatic cohort remedy
