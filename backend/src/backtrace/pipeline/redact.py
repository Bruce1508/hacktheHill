"""PII redaction (§8.2 step 1) — masks names, phone numbers, and addresses
before complaint text is sent to any external model."""

import re
from typing import Iterable

_PHONE_RE = re.compile(r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-z]+\s){1,3}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|"
    r"Way|Place|Pl|Terrace|Ter|Circle|Cir|Parkway|Pkwy|Trail|Trl|Highway|Hwy)\b",
    re.IGNORECASE,
)


def redact_text(text: str, customer_names: Iterable[str] = ()) -> str:
    """Mask known customer names (exact, case-insensitive), then phone
    numbers and street addresses via regex. Order matters: name redaction
    first, since a name can otherwise sit inside what looks like an address."""
    for name in customer_names:
        if name:
            text = re.sub(re.escape(name), "[NAME]", text, flags=re.IGNORECASE)
    text = _ADDRESS_RE.sub("[ADDRESS]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return text
