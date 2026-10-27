from decimal import Decimal

from backtrace.gate.rules import check_amount, check_forbidden_phrases, check_vulnerability

FORBIDDEN_PHRASES = ("guarantee", "lifetime", "unlimited")


def test_check_amount_passes_on_exact_match():
    result = check_amount(letter_text="we are issuing a credit of $1.75", expected_amount=Decimal("1.75"))
    assert result.passed is True


def test_check_amount_fails_on_mismatch():
    result = check_amount(letter_text="we are issuing a credit of $5.00", expected_amount=Decimal("1.75"))
    assert result.passed is False
    assert "1.75" in result.reason


def test_check_forbidden_phrases_blocks_commitment_language():
    result = check_forbidden_phrases(letter_text="we guarantee this will never happen again", forbidden_phrases=FORBIDDEN_PHRASES)
    assert result.passed is False
    assert "guarantee" in result.reason


def test_check_vulnerability_blocks_cohort_remedy():
    result = check_vulnerability(vulnerability_signals=["mentions hardship"])
    assert result.passed is False
    assert result.reason == "vulnerability_signals present: routes to individual review"


def test_check_amount_fails_when_letter_adds_an_unauthorized_amount():
    result = check_amount(letter_text="a credit of $1.75 plus an extra $50 goodwill credit", expected_amount=Decimal("1.75"))
    assert result.passed is False


def test_check_amount_allows_the_same_amount_stated_twice():
    result = check_amount(letter_text="a credit of $1.75 ... again, $1.75 total", expected_amount=Decimal("1.75"))
    assert result.passed is True
