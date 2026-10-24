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

# Citations are validated against the pack's own ids after the call
# (backtrace.pipeline.hypothesis._validate_citations) — any id not in the
# lists below gets the whole hypothesis rejected, so the model must only
# cite what it was given.
HYPOTHESIS_PROMPT_V1 = (
    "You are investigating the likely root cause shared by a cohort of "
    "customer complaints. Write a short root-cause hypothesis using ONLY "
    "the evidence below. Cite only ids that appear in the lists given — "
    "citing any other id is not allowed. If there is not enough evidence "
    "to support a hypothesis, write exactly \"no citable evidence\" as the "
    "hypothesis text and leave the citation lists empty.\n\n"
    "Complaint ids available to cite: {complaint_ids}\n"
    "Event ids available to cite: {event_ids}\n"
    "Anomaly ids available to cite: {anomaly_ids}\n"
    "Averaged linking-score components: {score_components}\n"
    "Sample complaint texts:\n{sample_texts}"
)

# §10.2: the amount, cause, and issues are pre-computed and fixed — the model
# only drafts prose around them. It must never state a different amount than
# the one given, and never promise anything beyond the credit itself (no
# extra compensation, no guarantees, no additional commitments) — the Gate
# (Task 8) re-checks both of these against the letter text.
LETTER_PROMPT_V1 = (
    "Write a short, professional customer-service letter responding to a "
    "service complaint. Use ONLY the facts given below. State the credit "
    "amount exactly as given — do not state any other amount. Do not "
    "promise anything beyond this credit (no additional compensation, no "
    "guarantees, no other commitments).\n\n"
    "Credit amount: ${amount}\n"
    "Cause: {claimed_cause}\n"
    "Issues reported: {issues}\n\n"
    "Return only the letter text."
)
