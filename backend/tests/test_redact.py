from backtrace.pipeline.redact import redact_text


def test_redacts_known_customer_name():
    text = "Jordan Alvarez called about a billing issue."
    redacted = redact_text(text, customer_names=["Jordan Alvarez"])
    assert "Jordan Alvarez" not in redacted
    assert "[NAME]" in redacted


def test_redacts_phone_number():
    text = "Call me back at 555-123-4567 please."
    redacted = redact_text(text)
    assert "555-123-4567" not in redacted
    assert "[PHONE]" in redacted


def test_redacts_street_address():
    text = "My service address is 742 Evergreen Terrace and it's still down."
    redacted = redact_text(text)
    assert "742 Evergreen Terrace" not in redacted
    assert "[ADDRESS]" in redacted


def test_leaves_unrelated_text_untouched():
    text = "My fiber_pro connection keeps dropping in north."
    assert redact_text(text) == text
