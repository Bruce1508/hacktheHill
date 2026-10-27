"""Consistency Gate rule checks (§10.3). Rules run before the LLM; a draft
that fails a rule spends no LLM tokens. Pure functions, no DB, no network."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class GateCheckResult:
    check: str
    passed: bool
    reason: str | None = None


_AMOUNT_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)")


def check_amount(letter_text: str, expected_amount: Decimal) -> GateCheckResult:
    matches = _AMOUNT_RE.findall(letter_text)
    if not matches:
        return GateCheckResult("amount", False, "no dollar amount found in letter")
    try:
        found = [Decimal(m) for m in matches]
    except InvalidOperation:
        return GateCheckResult("amount", False, "unparseable amount in letter")
    if expected_amount not in found:
        return GateCheckResult("amount", False, f"letter amount(s) {found} do not match remedy amount {expected_amount}")
    return GateCheckResult("amount", True)


def check_forbidden_phrases(letter_text: str, forbidden_phrases: tuple[str, ...]) -> GateCheckResult:
    lowered = letter_text.lower()
    for phrase in forbidden_phrases:
        if phrase in lowered:
            return GateCheckResult("forbidden_phrases", False, f"forbidden phrase: {phrase!r}")
    return GateCheckResult("forbidden_phrases", True)


def check_vulnerability(vulnerability_signals: list[str]) -> GateCheckResult:
    if vulnerability_signals:
        return GateCheckResult("vulnerability", False, "vulnerability_signals present: routes to individual review")
    return GateCheckResult("vulnerability", True)


def check_cohort_consistency(member_amount: Decimal, cohort_min: Decimal, cohort_max: Decimal) -> GateCheckResult:
    if not (cohort_min <= member_amount <= cohort_max):
        return GateCheckResult("cohort_consistency", False, f"amount {member_amount} outside cohort range [{cohort_min}, {cohort_max}]")
    return GateCheckResult("cohort_consistency", True)
