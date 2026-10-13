"""Versioned prompt templates (§8.5). A prompt-text edit here must bump the
matching prompt_version in configs/pipeline.yaml — that version bump is what
makes it an intentional llm_cache miss, not a silent behavior change."""

EXTRACTION_PROMPT_V1 = (
    "Extract structured fields from this customer complaint. "
    "Return only fields defined by the response schema; do not invent facts "
    "not present in the text.\n\nComplaint:\n{text}"
)

# Only the observable TextSeed fields may appear here (see TextSeed's
# docstring in backtrace_eval.generator.dev) — never the gold root cause.
DEV_TEXT_PROMPT_V1 = (
    "Write a short, realistic customer complaint message (2-4 sentences, "
    "first person, no greeting or signature) a telecom customer would send "
    "to support. Vary the wording naturally; do not use a template. Use "
    "ONLY the facts listed below — do not invent a city, date, time, prior "
    "contact, or any other specific detail not given below; if a field "
    "says \"none\", do not mention it at all.\n\n"
    "Context:\n"
    "- product/plan: {product}\n"
    "- region: {region}\n"
    "- channel: {channel}\n"
    "- persona/tone: {persona}\n"
    "- main issue: {symptom}\n"
    "- customer's guess at the cause: {claimed_cause}\n"
    "- secondary issue also mentioned: {secondary_symptom}\n"
    "- this is a repeat contact about the same issue: {is_repeat}\n"
    "- customer mentions needing accessibility/priority help: {vulnerability_mentioned}\n\n"
    "Return only the complaint text."
)
