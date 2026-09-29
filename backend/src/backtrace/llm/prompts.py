"""Versioned prompt templates (§8.5). A prompt-text edit here must bump the
matching prompt_version in configs/pipeline.yaml — that version bump is what
makes it an intentional llm_cache miss, not a silent behavior change."""

EXTRACTION_PROMPT_V1 = (
    "Extract structured fields from this customer complaint. "
    "Return only fields defined by the response schema; do not invent facts "
    "not present in the text.\n\nComplaint:\n{text}"
)
