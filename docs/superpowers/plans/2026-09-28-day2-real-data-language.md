# Day 2 — Real data + language implementation plan

**Status:** Phases 1–2 implemented and verified against a live Postgres/Timescale container on `day2-real-data-language`, based on `main` at `4e3946d`. Phase 2 pinned `complaint_embeddings.embedding` to `vector(768)` as a placeholder — confirm the real Gemini output_dimensionality before Phase 3 and adjust with a follow-up migration if it differs. Phases 3–6 not started; Phase 3/6 need a Gemini API key (pending).

**Goal:** meet the Day 2 row of `Backtrace — Technical Design Doc.md` §19: generate and load the `dev` synthetic world; extract structured fields and embeddings with Gemini and a persistent cache; run the stages through one Postgres-backed worker; show the `dev` complaints in a basic deck.gl scatter. A repeated run over the same input must make zero Gemini calls.

**Out of scope for Day 2:** HDBSCAN, anomaly detection, burst detection, event linking, root-cause cohorts, remedy decisions, approval, Auth0, hybrid retrieval, held-out/demo generation, and a separate broker. These belong to later days in §19. Day 2's point positions do not assert root cause.

## Phase 0 — documentation discovery and decisions

Read these before coding; the design doc is the source of truth (§6.1, §19):

| Concern | Project source / copy-ready pattern | Verified external API |
| --- | --- | --- |
| Dev-world size and data wall | Design §5.1–5.8; `backend/src/backtrace_eval/generator/tiny.py:6-96`, `generator/cli.py:10-31`, `generator/load.py:10-56` | — |
| App/eval schema and run tables | Design §7.1–7.2; migrations `0001_schemas_and_roles.py`, `0002_core_tables.py`; `db/models.py:1-47` | [pgvector Python SQLAlchemy mapping](https://github.com/pgvector/pgvector-python#sqlalchemy) |
| Extraction and cache | Design §8.2 steps 1–3, §8.5; `contracts/extraction.py:4-15` | [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output) |
| Embeddings | Design §8.2 step 3, §6.3 model config | [Gemini embeddings API](https://ai.google.dev/api/embeddings) |
| Jobs | Design §11; `db/session.py:8-15` | [SQLAlchemy `with_for_update(skip_locked=True)`](https://docs.sqlalchemy.org/en/20/core/selectable.html) |
| Web scatter | Design §6.5 `/viz/complaints`, §7.1 `complaint_layout`; `apps/web/src/app/page.tsx`, `src/lib/api.ts` | [deck.gl React](https://deck.gl/docs/get-started/using-with-react), [ScatterplotLayer](https://deck.gl/docs/api-reference/layers/scatterplot-layer), [OrthographicView](https://deck.gl/docs/api-reference/core/orthographic-view) |
| Next.js server/client boundary | `apps/web/AGENTS.md`; installed `apps/web/node_modules/next/dist/docs/01-app/01-getting-started/05-server-and-client-components.md` | — |

Allowed API examples to copy and adapt, after pinning dependency versions: `genai.Client().interactions.create(..., response_format={"type": "text", "mime_type": "application/json", "schema": ComplaintExtraction.model_json_schema()})` with `ComplaintExtraction.model_validate_json(...)`; `client.models.embed_content(..., config=types.EmbedContentConfig(output_dimensionality=...))`; `mapped_column(VECTOR(n))`; `select(Job).with_for_update(skip_locked=True)`; `DeckGL` + `ScatterplotLayer` + `OrthographicView`. Verify these signatures against the installed versions during implementation. Do not assume that a newer SDK shares an older `generate_content` example's parameters.

Lock these decisions before creating the vector migration or making paid calls:

1. Day 1 is merged; `main`/`origin/main` are at `4e3946d`. `day2-real-data-language` branches from there.
2. Confirm available Gemini model IDs and account quota in AI Studio / `models.list`; pin **separate** text-generation and extraction model IDs, the embedding model, output dimension, prompt versions, and a maximum dev-run call/spend budget in `configs/pipeline.yaml`. This addresses design §6.3 and open question §20. A 20-complaint smoke run precedes the full `dev` run. Keep API keys only in `.env`.
3. Record a `dev` seed and event config separate from any future held-out seed/config. Define what is committed (world config and tests) and what stays local/ignored (large generated data, generated text cache, and held-out material). Never commit a held-out configuration before freeze (§5.8).
4. For Day 2 only, derive deterministic provisional `(x, y)` positions from embeddings (for example, PCA with fixed preprocessing/seed). Save `layout_version`. `cohort_id` and `symptom_cluster_id` are nullable until Day 3; the UI must call this a symptom/embedding view, not a root-cause result.

Phase 0 verification: selected model IDs exist for the account, a small extraction and embedding response validates against the intended schemas/dimension, the selected embedding dimension fits the local pgvector type, and Day 1's accepted branch is clean. Do not run a full 1–2k-complaint LLM batch before these checks.

## Phase 1 — dev-world contract and pure generator

**Implement:** add `configs/worlds/dev.yaml` and a dev-world generator under `backend/src/backtrace_eval/generator/`, using the `TinyWorldConfig` / `generate_tiny_world` pattern rather than scaling up the four tiny text templates. Keep pure world construction separate from I/O and LLM text realization. Generate approximately 5,000 customers, 1,000–2,000 complaints, 6–8 planted causes, 6–10 regions, topology/customer-node mapping, observable event traces, telemetry including decoys, 15–25% one-off complaints, misattribution, overlapping events, mixed network and non-network causes, repeat/multi-issue complaints, and distinct products (§5.1–5.7).

The generator first creates structured cause/persona/complaint seeds and hidden labels. A separate, versioned Gemini generation step realizes varied complaint text from those seeds using a model/prompt different from extraction; cache its outputs so a run is reproducible. A deterministic fake provider supplies CI tests and the 20-row smoke fixture. Manifest: seed, config hash, generation model, prompt version, counts, and output hashes. Keep app-visible data and hidden `eval` labels in separate files/objects from the first write.

**Verify:** same seed/config/cache yields byte-stable output; config-driven counts and proportions are asserted; there are both network and non-network causes and at least one overlap/decoy; app-visible rows contain no `root_cause_id`, gold remedy, or vulnerability answer key. No live Gemini call runs in CI.

**Guard:** do not import `backtrace_eval` from `backtrace`; do not place true-cause IDs or gold labels in app-visible complaint text, prompts sent by the pipeline, or observable event rows. Do not use the `demo` or held-out profile for Day 2 tuning.

## Phase 2 — migrations, loader, and role separation

**Implement:** use explicit Alembic migrations after `0002_core_tables.py`, preserving the existing schemas/grants pattern:

- World storage: `app.network_nodes`, `app.network_links`, observable `app.events` extensions as needed, `app.telemetry` (Timescale hypertable if the extension is installed), and required complaint/customer fields; `eval.gold_events` and `eval.gold_complaint_labels` with enough detail for later evaluation.
- Pipeline storage: `app.pipeline_runs`, `app.complaint_features`, `app.complaint_embeddings` with `VECTOR(pinned_dimension)`, `app.llm_cache`, `app.llm_calls`, `app.jobs`, and `app.complaint_layout`. Key stage outputs by `run_id` plus complaint/model/version so retries and reruns are idempotent. A uniqueness constraint should prevent duplicate cache keys and duplicate job/run stage records.
- Expand the eval-role fixture loader from `generator/load.py:10-56` to load both schemas in dependency order. Give dev IDs their own namespace or perform an explicit, scoped reseed so `tiny` and `dev` cannot silently mix. Verify table and sequence privileges for `bt_eval`/`bt_pipeline` after migration.

**Verify:** migrate a fresh local DB; load a smoke world and the full dev world; counts match the manifest; `bt_pipeline` can read/write app stage tables but gets permission denied on eval tables; `bt_eval` can load both schemas; `test_import_rules.py` still passes; reseeding the same dev run does not duplicate rows.

**Guard:** extension availability in README is not proof that `CREATE EXTENSION vector` has run. Keep migrations owner-only; do not put gold labels, gold-derived fields, or detailed missed cases in `app`.

## Phase 3 — PII redaction, Gemini adapters, and persistent cache

**Implement:** add focused modules under `backtrace/pipeline/` and `backtrace/llm/`. Redact names, phones, and addresses, using customer profile names where present, **before** passing complaint text to an external model (§8.2). Build a small provider interface with real Gemini and fake/cache-only implementations. Use the Pydantic `ComplaintExtraction` contract for structured output; validate every response, retry a schema failure once, then mark that complaint `needs_review` without hiding the failure. Embed only redacted text plus the validated symptom summary.

Persist both extraction and embedding results in `llm_cache`. Derive keys from canonical serialized model ID, prompt version, request text, embedding task type/dimension, and all other output-affecting settings. Store `llm_calls` rows with model, stage, tokens, latency, cache hit, and cost estimate; cached calls must record zero newly spent tokens. Pin prompt text/version in a registry or config. Bound concurrency according to the account's real RPM/TPM limits, retry transient rate limits with backoff, and prohibit network calls in `cache_only` mode (§8.5, §14).

**Verify:** redaction tests assert no seeded name/phone/address reaches the fake provider; extraction validates the exact contract; invalid output retries once then records review status; changing prompt/model/dimension changes the cache key; an identical request hits cache with no provider call; fake-provider tests run without an API key. Complete a small live smoke run only after Phase 0's quota check.

**Guard:** Gemini output is never used for money or ground-truth labels; do not cache raw unredacted complaint text in app-visible LLM tables; do not confuse the project's persistent response cache with Gemini's context-caching API.

## Phase 4 — idempotent batch stages and one worker

**Implement:** add extraction and embedding stages that read only `app`, write per-run rows, and can resume after interruption. Reuse one SQLAlchemy engine/session factory per worker process rather than calling the current `get_session()` (which constructs/disposes an engine) for each complaint. Add a `jobs` repository and one worker loop using `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` (§11); claim/commit a job before slow Gemini work, then update status in a separate transaction. Support `pipeline.run` and `pipeline.stage` now; add `letters.draft` when drafting exists on Day 4. Include bounded retries, stale-running-job recovery, heartbeat, and structured logs with `run_id`/`job_id`.

Add a real `worker` service to Compose only when the dequeue loop exists. Add Makefile commands to generate/load `dev`, enqueue a pipeline run, inspect run/job status, and rerun the same input. Add `GET /jobs/{id}` and `GET /runs/latest` using Pydantic DTOs, dev auth, and only app-schema data. Update `/health` to report worker heartbeat as specified by §11, without making Day 1's API health dependent on Gemini availability.

**Verify:** two worker claim attempts cannot take the same job; killing/restarting the worker resumes or retries a staged job without duplicate features/embeddings; a failed complaint is visible with reason; run status/counts and heartbeat are observable; the application role still cannot access eval. Test on smoke data before full dev.

**Guard:** no Redis/RQ/Kafka or second worker process; no eval task runs inside the pipeline worker; no DB transaction remains open during a slow Gemini request.

## Phase 5 — provisional layout, API, and deck.gl scatter

**Implement:** compute reproducible provisional 2D coordinates from the completed dev embeddings and save them in `app.complaint_layout` with `run_id` and version. Add authenticated `GET /viz/complaints` returning a bounded whole-run point set (`complaint_id`, `x`, `y`, nullable `cohort_id`/`symptom_cluster_id`, `claimed_cause`) plus run/profile/`synthetic` metadata. Do not paginate this through the existing `/complaints` route; that endpoint is capped at 100 rows and is not the visual-data contract (§6.5).

In Next.js, retain the server-side `API_URL` fetch and demo identity pattern from `src/lib/api.ts`, then pass serializable points to a small Client Component. Add version-aligned `@deck.gl/react`, `@deck.gl/layers`, and `@deck.gl/core`; use an `OrthographicView` for non-geographic XY and a `ScatterplotLayer` with `getPosition`, color/radius, pickability, and a basic tooltip. Isolate browser-only WebGL rendering from the Server Component, following the installed Next docs named in Phase 0. Replace the hard-coded `(tiny)` heading with the actual run/profile and a visible `synthetic` label.

**Verify:** API returns exactly the completed dev point count with unique IDs and finite coordinates; no eval field appears in JSON; the browser visibly renders all points and reports the same count; frontend lint/build pass; the existing tiny list/health path still works.

**Guard:** do not label provisional proximity as a verified cause or cohort; do not depend on a live map tile service or browser access to the private API URL. If deck.gl SSR fails, use the official client-only boundary pattern rather than weakening server-side auth.

## Phase 6 — Day 2 end-to-end gate

Run the complete sequence from a reproducible local database and record evidence in README:

1. Generate/load `dev`; verify approximately 5,000 customers, 1,000–2,000 complaints, 6–8 causes, and correct separation of observable app data from eval truth.
2. Run extraction and embeddings through the worker; assert one valid feature and one vector of the pinned dimension for **every** dev complaint, with no unresolved `needs_review` in the accepted run. Store the run's config, seed, model IDs, prompt versions, stage timings, and real token usage.
3. Start a **new** run ID over the same inputs with the same models/prompts; assert zero Gemini provider calls and zero newly spent tokens. Also retry an interrupted job to prove idempotent writes. Reusing only the old run ID would test stage skipping, not the persistent cache.
4. Show the `dev` scatter in the browser and match its point count with DB/API counts; make the synthetic label and provisional-layout meaning visible.
5. Run backend tests, frontend lint/build, `git diff --check`, and the `backtrace`→`backtrace_eval` import-rule test. Scan for hard-coded model IDs outside config, `backtrace_eval` imports inside `backtrace`, unbounded Gemini call loops, and gold fields in app/API DTOs. Record any environment-only build limitations separately from code failures.

**Done when:** the §19 Day 2 criterion is demonstrated and documented: all dev complaints extracted and embedded, a fresh rerun makes zero Gemini calls, and the scatter shows the dev points. Review each phase's diff and commit in focused chunks so a later session can resume from Git history. Do not begin Day 3 linking until this gate passes.
