# Day 3 — Root cause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Compact plan (by choice, 2026-10-17):** architecture, interfaces, config values and test assertions are fixed here; implementers write the code. Every task is TDD: write the listed tests → see them fail → implement → see them pass → commit.

**Goal:** Meet the Day 3 row of `Backtrace — Technical Design Doc.md` §19: symptom clusters, telemetry anomalies, complaint bursts and evidence-linked cohorts are in the DB for `dev`, a first A/B/C ablation report exists, and the T2-vs-T1 narrative decision is recorded.

**Architecture:** Four new batch stages — `anomaly`, `burst`, `clustering`, `linking` — each split into a **pure core** (numpy/list in → plain data out, unit-tested with no DB) and a thin `run_<x>_stage(session_factory, run_id) -> dict` that loads, calls the core, and does delete-by-`run_id`-then-insert in one transaction (same idempotency pattern as `run_layout_stage` in `backend/src/backtrace/pipeline/layout.py`). The worker runs them after `embedding`, before `layout`. None of them call an LLM, so the Day 2 zero-token rerun property is preserved. Ablation lives in `backtrace_eval` (the only side allowed to read gold labels) and reuses the pure clustering core.

**Tech Stack:** Python 3.13, NumPy, **scikit-learn ≥ 1.3** (new dependency: `sklearn.cluster.HDBSCAN`, `sklearn.decomposition.PCA`, `sklearn.metrics` — one dependency instead of `hdbscan` + a metrics lib), SQLAlchemy/Alembic, Postgres 16 + Timescale + pgvector.

**Spec:** `Backtrace — Technical Design Doc.md` §5.4–5.7, §7.1, §8.2 steps 4–7, §8.3, §13.2–13.3, §19 (Day 3 row). Predecessor: `docs/superpowers/plans/2026-09-28-day2-real-data-language.md`.

## Global Constraints

- `backtrace` must never import `backtrace_eval` (`backend/tests/test_import_rules.py` enforces it). `backtrace_eval` may import `backtrace`.
- The pipeline (`bt_pipeline` role) never reads the `eval` schema. No weight, threshold, or parameter is tuned against gold labels — all live in `configs/pipeline.yaml`.
- `semantic` is weighted lower than every operational linking component (thesis T2, §8.3).
- Two candidates with close scores → `needs_review`, never an automatic choice (§8.3).
- Fixed seeds for PCA (§8.5): same `run_id` inputs + config ⇒ identical output.
- Each stage is idempotent per `run_id`: re-running it replaces, never duplicates.
- Out of scope for Day 3: Gemini hypothesis (§8.2 step 8), cohort-centroid layout (step 9), review UI, remedies, hybrid retrieval, online path, `make eval`/`eval_results` persistence (Day 5), held-out data.

## Data gate (read before Task 8)

Tasks 1–7 are developed and tested on the fake provider and on the existing `dev-run-2` (templated text). The **accepted** Day 3 run is on `dev-run-3`, which needs the real-Gemini text regen at 1,600/1,600 first (746/1,600 as of 2026-10-17), then reload + extraction + embedding. Templated text has only 828 distinct strings, so ablation A/B numbers on `dev-run-2` will be optimistic — do not record the T2/T1 decision from them.

## File structure

| File | Responsibility |
| --- | --- |
| `backend/pyproject.toml` | add `scikit-learn>=1.3` |
| `configs/pipeline.yaml` | new `anomaly`, `burst`, `clustering`, `linking` sections |
| `backend/src/backtrace/llm/config.py` | typed params dataclasses for the new sections (file keeps its name; it already owns `pipeline.yaml`) |
| `backend/alembic/versions/0005_root_cause_tables.py` | `detected_anomalies`, `complaint_bursts`, `symptom_clusters`, `symptom_cluster_members`, `cohorts`, `cohort_members`, `cohort_event_links` |
| ORM models module (confirm path: `grep -rn "class ComplaintLayout" backend/src`) | ORM models for the new tables |
| `backend/src/backtrace/pipeline/anomaly.py` | rolling z-score core + stage |
| `backend/src/backtrace/pipeline/burst.py` | 15-min complaint-count burst core + stage |
| `backend/src/backtrace/pipeline/clustering.py` | PCA→HDBSCAN core + stage |
| `backend/src/backtrace/pipeline/linking.py` | §8.3 scoring, assignment, cohort grouping + stage |
| `backend/src/backtrace/worker/main.py` | stage order |
| `backend/src/backtrace_eval/ablation.py` | A/B/C ablation + metrics + Markdown report CLI |
| `backend/tests/test_pipeline_{anomaly,burst,clustering,linking}.py`, `backend/tests/test_ablation.py` | tests |

---

### Task 1: Dependency, config, migration, models

**Files:** Modify `backend/pyproject.toml`, `configs/pipeline.yaml`, `backend/src/backtrace/llm/config.py`, ORM models module. Create `backend/alembic/versions/0005_root_cause_tables.py`. Test: extend `backend/tests/test_models.py`; config part in a new `backend/tests/test_root_cause_config.py`.

**Interfaces — Produces:**

```python
@dataclass(frozen=True)
class AnomalyParams:   window_points: int; z_threshold: float; min_points: int; metrics: tuple[str, ...]
@dataclass(frozen=True)
class BurstParams:     bucket_minutes: int; baseline_buckets: int; z_threshold: float; min_count: int
@dataclass(frozen=True)
class ClusterParams:   pca_dims: int; min_cluster_size: int; min_samples: int; structured_weight: float; seed: int
@dataclass(frozen=True)
class LinkParams:      weights: Mapping[str, float]; threshold: float; ambiguity_margin: float;
                       lag_max_minutes: int; temporal_tau_minutes: float
# PipelineConfig gains: anomaly: AnomalyParams, burst: BurstParams, clustering: ClusterParams, linking: LinkParams
```

`configs/pipeline.yaml` additions (starting values; comment the block as "hand-set, never fit to gold labels"):

```yaml
anomaly:    {window_points: 48, z_threshold: 4.0, min_points: 2, metrics: [packet_loss_pct, errored_seconds, optical_power_dbm]}
burst:      {bucket_minutes: 15, baseline_buckets: 96, z_threshold: 3.0, min_count: 5}
clustering: {pca_dims: 20, min_cluster_size: 15, min_samples: 5, structured_weight: 0.5, seed: 20261017}
linking:
  weights: {scope_match: 3.0, region_node_overlap: 1.0, temporal: 2.0, telemetry: 2.0, burst: 1.0, semantic: 0.5}
  threshold: 3.5
  ambiguity_margin: 0.5
  lag_max_minutes: 720
  temporal_tau_minutes: 180
```

Migration 0005 tables (all in schema `app`, all with `run_id` text not null and an index on `run_id`; grants to `bt_pipeline` follow migration 0003's pattern):

| Table | Columns |
| --- | --- |
| `detected_anomalies` | `id` text PK (`anom-<run>-<n>`), `run_id`, `node_id` text null, `link_id` text null, `metric` text, `start_at`/`end_at` timestamptz, `peak_score` float, `method` text (`rolling_z_v1`) |
| `complaint_bursts` | `id` text PK, `run_id`, `region` text, `start_at`/`end_at`, `complaint_count` int, `peak_score` float |
| `symptom_clusters` | `id` text PK, `run_id`, `label` int (HDBSCAN label ≥ 0), `size` int, `method` text (`text` \| `text+structured`) |
| `symptom_cluster_members` | `run_id`, `complaint_id`, `cluster_id` text **null** (null = noise); PK (`run_id`, `complaint_id`) |
| `cohorts` | `id` text PK, `run_id`, `status` text default `proposed`, `kind` text (`linked` \| `no_linked_evidence`), `hypothesis` text null, `hypothesis_citations` jsonb null, `confidence` float null |
| `cohort_members` | `cohort_id` FK, `complaint_id`, `run_id`, `membership_score` float, `assigned_by` text (`batch`), `needs_review` bool; PK (`cohort_id`, `complaint_id`) |
| `cohort_event_links` | `cohort_id` FK, `run_id`, `event_id` text null, `anomaly_id` text null, `overlap_score` float, `time_offset_minutes` float null, `evidence` jsonb |

**Tests:**
- `PipelineConfig.load()` returns the new sections with the YAML values above; `linking.weights["semantic"]` < every other weight (the T2 constraint is encoded, not just documented).
- `alembic upgrade head` → `downgrade -1` → `upgrade head` succeeds on the live test DB; `bt_pipeline` can insert/select each new table and **cannot** select `eval.gold_complaint_labels` (re-assert the wall).

- [ ] Tests → fail → implement → `cd backend && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q` → commit `feat(db): Day 3 root-cause tables, params, scikit-learn`

---

### Task 2: Telemetry anomaly detection (§8.2 step 4)

**Files:** Create `backend/src/backtrace/pipeline/anomaly.py`, `backend/tests/test_pipeline_anomaly.py`.

**Interfaces — Produces:**

```python
@dataclass(frozen=True)
class Anomaly: series_key: tuple[str | None, str | None]  # (node_id, link_id)
               metric: str; start_at: datetime; end_at: datetime; peak_score: float
def detect_anomalies(timestamps: Sequence[datetime], values: np.ndarray, *, series_key, metric: str, params: AnomalyParams) -> list[Anomaly]
def run_anomaly_stage(session_factory, run_id: str, params: AnomalyParams) -> dict   # {"anomalies": n}
```

Core: per series (`app.telemetry` has both node samples with `link_id` null and link samples — key on `(node_id, link_id)`), z = (v − mean_prev) / std_prev over the previous `window_points` samples (exclude the current point so a spike can't mask itself); for `optical_power_dbm` flag **drops** (use −z). Flag z ≥ `z_threshold`; merge consecutive flagged points into one interval; drop intervals shorter than `min_points`. If std_prev == 0: z = 0 when the value equals the mean, else z = +∞ (a jump off a perfectly flat baseline must fire). Telemetry is not run-scoped, so the stage reads all of `app.telemetry` and writes anomalies under `run_id`.

**Tests (pure):**
- flat series of 200 points + 10-point `packet_loss_pct` spike at index 120 → exactly one anomaly, `start_at == ts[120]`, `end_at == ts[129]`.
- 1-point spike with `min_points=2` → none.
- `optical_power_dbm` dropping −20 → −30 → detected; rising to −10 → not detected.
- flat series → none.
- **Stage (live DB):** load the `dev` fixture telemetry, run twice → same row count (idempotent); at least one anomaly overlaps each `dev` network gold event window — the *test* reads gold via the `bt_eval` loader, never the stage.

- [ ] TDD steps → commit `feat(pipeline): Day 3 telemetry anomaly stage (rolling z-score)`

---

### Task 3: Complaint burst detection (§8.2 step 5)

**Files:** Create `backend/src/backtrace/pipeline/burst.py`, `backend/tests/test_pipeline_burst.py`.

**Interfaces — Produces:**

```python
@dataclass(frozen=True)
class Burst: region: str; start_at: datetime; end_at: datetime; complaint_count: int; peak_score: float
def detect_bursts(received_at_by_region: Mapping[str, Sequence[datetime]], *, window_start: datetime, window_end: datetime, params: BurstParams) -> list[Burst]
def run_burst_stage(session_factory, run_id: str, params: BurstParams) -> dict   # {"bursts": n}
```

Core: bucket per region into `bucket_minutes` bins across the whole window (empty bins = 0 — they matter for the baseline); baseline = mean/std of the previous `baseline_buckets` bins; flag bins with count ≥ `min_count` and z ≥ `z_threshold`; merge adjacent flagged bins. Region only (event scopes in `dev` are region-level; node-level bursts are YAGNI until the data has node scopes). Stage input = complaints that have features under `run_id`, joined to customers for region.

**Tests (pure):** steady 1 complaint/bucket for 2 days in `north` + 20 complaints inside 30 min → one burst covering those 2 buckets; same 20 spread over 2 days → none; a `north` burst creates nothing in `south`; 4 complaints in one bucket with `min_count=5` → none. Stage: idempotent rerun.

- [ ] TDD steps → commit `feat(pipeline): Day 3 complaint burst stage`

---

### Task 4: Symptom clustering (§8.2 step 6)

**Files:** Create `backend/src/backtrace/pipeline/clustering.py`, `backend/tests/test_pipeline_clustering.py`.

**Interfaces — Produces (Task 7 reuses `cluster_symptoms` and `structured_matrix`):**

```python
def structured_matrix(products: Sequence[str], regions: Sequence[str]) -> np.ndarray   # one-hot, sorted category order
def cluster_symptoms(vectors: np.ndarray, *, params: ClusterParams, structured: np.ndarray | None = None) -> np.ndarray  # labels, -1 = noise
def run_clustering_stage(session_factory, run_id: str, params: ClusterParams) -> dict  # {"clusters": k, "noise": n}
```

Core: L2-normalize → `PCA(n_components=min(pca_dims, n-1, d), random_state=params.seed)` → if `structured` given, `hstack([reduced, structured_weight * structured])` → `HDBSCAN(min_cluster_size=..., min_samples=...).fit_predict`. The stage uses **text + structured** (product from `complaint_features.extraction["product"]`, region from the customer). Writes `symptom_clusters` (method `text+structured`) and one `symptom_cluster_members` row per complaint (null `cluster_id` for noise).

**Tests (pure):** three well-separated Gaussian blobs in 768-d (60 points each, fixed rng) + 10 uniform outliers → 3 clusters with pure blob membership, ≥ 5 outliers labelled −1; same input twice → identical labels; two blobs overlapping in vector space but differing in the region one-hot → separated only when `structured` is passed. Stage: idempotent; every complaint with an embedding has exactly one member row.

- [ ] TDD steps → commit `feat(pipeline): Day 3 symptom clustering stage (PCA + HDBSCAN)`

---

### Task 5: Evidence linking → cohorts (§8.3)

**Files:** Create `backend/src/backtrace/pipeline/linking.py`, `backend/tests/test_pipeline_linking.py`.

**Interfaces — Consumes:** `Burst` (Task 3), anomaly rows (Task 2), cluster members (Task 4). **Produces:**

```python
@dataclass(frozen=True)
class Candidate: id: str; kind: Literal["event", "anomaly"]; start_at: datetime; end_at: datetime
                 region: str | None; node_ids: frozenset[str]; customer_ids: frozenset[str] | None
@dataclass(frozen=True)
class ComplaintCtx: complaint_id: str; customer_id: str; region: str; node_id: str
                    received_at: datetime; vector: np.ndarray; cluster_id: str | None
COMPONENTS = ("scope_match", "region_node_overlap", "temporal", "telemetry", "burst", "semantic")
def score_components(c: ComplaintCtx, cand: Candidate, *, anomalies: Sequence[Candidate], bursts: Sequence[Burst],
                     centroid: np.ndarray | None, params: LinkParams) -> dict[str, float]   # each in [0, 1]
def total_score(components: Mapping[str, float], weights: Mapping[str, float]) -> float
def assign(scores: Mapping[str, float], params: LinkParams) -> tuple[str | None, bool]  # (candidate_id, needs_review)
def group_candidates(cands: Sequence[Candidate]) -> list[frozenset[str]]  # union-find
def run_linking_stage(session_factory, run_id: str, params: LinkParams) -> dict  # {"cohorts","linked","no_evidence","needs_review","noise"}
```

Component rules (each stored separately — §8.3 table):
- `scope_match` = 1 if `cand.customer_ids` contains the customer, or (anomaly) the customer's `node_id` ∈ `cand.node_ids` (the anomalous node itself, or `to_node_id` of the anomalous link per `app.network_links`); else 0. A region-only event scope → 0 here (that is `region_node_overlap`'s job).
- `region_node_overlap` = 1 if same region.
- `temporal` = 1 if `start_at ≤ received_at ≤ end_at`; `exp(−lag/tau)` for `0 < lag ≤ lag_max` after `end_at`; 0 otherwise (incl. before `start_at`).
- `telemetry` = 1 if an anomaly on the customer's node overlaps the candidate window (for anomaly candidates: equals `scope_match`).
- `burst` = 1 if a burst in the customer's region overlaps the candidate window.
- `semantic` = max(0, cosine(vector, centroid)), centroid = mean vector of pass-1 members. **Two passes:** pass 1 with `semantic = 0` assigns; pass 2 recomputes with pass-1 centroids and assigns again (final).

Assignment: best candidate if `total ≥ threshold`; if `best − second < ambiguity_margin` → `needs_review = True`, still recorded on the best cohort (visible membership, no money decided — Day 4 review resolves it). Grouping: union-find over candidates sharing a region with overlapping windows where at least one is an anomaly on a node in that region (alarm + anomaly on the same link ⇒ one cohort). Unassigned complaints with a `cluster_id` → one `no_linked_evidence` cohort per symptom cluster; noise stays out of every cohort. `cohort_event_links.evidence` = `{component: fraction of members with component > 0}`; `overlap_score` = mean member total.

**Tests (pure, synthetic fixtures built in the test):**
- complaint inside an event window, same region, node with an overlapping anomaly → assigned to that cohort; `temporal == 1`, `telemetry == 1`.
- **overlap case (§5.7):** two candidates, same region, same time; anomaly on node A only → complaint on node A goes to the anomaly-group cohort; complaint on node B is `needs_review` or elsewhere — **never** silently merged into A's cohort.
- 2 h after `end_at` with `tau=180` → `temporal ≈ exp(−120/180)`; 1 min before `start_at` → 0.
- semantic-only match (no region/time overlap) never reaches `threshold` with the config weights (encodes T2).
- `assign({"e1": 5.0, "e2": 4.8})` → `("e1", True)`; `{"e1": 5.0, "e2": 3.0}` → `("e1", False)`; all below threshold → `(None, False)`.
- unassigned clustered complaints → one `no_linked_evidence` cohort per cluster; noise → no cohort.
- Stage (live DB, `dev-run-2`): idempotent; every complaint in ≤ 1 cohort; every `linked` cohort has ≥ 1 `cohort_event_links` row.

- [ ] TDD steps → commit `feat(pipeline): Day 3 evidence linking → cohorts (§8.3)`

---

### Task 6: Worker wiring + end-to-end on an existing run

**Files:** Modify `backend/src/backtrace/worker/main.py` (`_run_job`); test in `backend/tests/test_pipeline_stages.py`.

`pipeline.run` stage order becomes `("extraction", "embedding", "anomaly", "burst", "clustering", "linking", "layout")`; each new stage is also runnable alone via `job.stage`. Params come from `config.anomaly` / `config.burst` / `config.clustering` / `config.linking`.

**Tests:** fake-provider `pipeline.run` on a small `dev` subset completes all 7 stages and writes rows to every new table; a rerun under a **new** `run_id` with `cache_only=True` spends 0 tokens (new stages add no `llm_calls` rows). Then run `run_cli` on `dev-run-2` for real and record row counts per table in this plan's Status block.

- [ ] TDD steps → commit `feat(worker): run Day 3 root-cause stages in pipeline.run`

---

### Task 7: Ablation A/B/C (§13.3) + report

**Files:** Create `backend/src/backtrace_eval/ablation.py`, `backend/tests/test_ablation.py`; add `reports/` to `.gitignore`.

**Interfaces — Consumes:** `cluster_symptoms`, `structured_matrix` (Task 4); `app.cohort_members` (Task 5). **Produces:**

```python
def clustering_metrics(true: Sequence[str | None], pred: Sequence[str | None]) -> dict[str, float]
    # ari, nmi, homogeneity, completeness (sklearn.metrics), false_merge_rate, cause_recall
def run_ablation(database_url_eval: str, run_id: str, params: ClusterParams) -> dict[str, dict[str, float]]  # {"A": {...}, "B": {...}, "C": {...}}
def main() -> None   # python -m backtrace_eval.ablation --run-id dev-run-3 --out reports/ablation-<run_id>.md
```

- **A** = `cluster_symptoms(vectors)` (text only). **B** = `cluster_symptoms(vectors, structured=...)`. **C** = cohorts from `app.cohort_members` for `run_id`.
- `true` = `eval.gold_complaint_labels.root_cause_id` (null for one-offs). Each predicted-noise/unassigned complaint gets its own singleton label for ARI/NMI.
- `false_merge_rate` = share of predicted groups of size ≥ 5 whose second-most-common true cause is ≥ 20 % of members (fixed definition, stated in the report).
- `cause_recall` = fraction of true causes having ≥ 1 predicted group with precision ≥ 0.8 for that cause.
- Report: Markdown table A/B/C × metrics + run_id, config hash, seed, date → `reports/` (regenerated, not committed; the *decision* goes in the design doc).

**Tests:** perfect prediction → `ari == 1`, `false_merge_rate == 0`; two causes merged into one group → that group counts as a false merge, `homogeneity < 1`; over-split → `homogeneity == 1`, `completeness < 1`. `test_import_rules.py` still green.

- [ ] TDD steps → commit `feat(eval): Day 3 A/B/C ablation report`

---

### Task 8: Day 3 gate (on `dev-run-3`)

Blocked until the dev-text regen reaches 1,600/1,600 (see Data gate).

1. Reload `dev` with regenerated text; run `pipeline.run` as `dev-run-3` (extraction ~1,600 `generate_content` calls ⇒ ≥ 4 Free Tier days at 500/day; embeddings use a separate quota). Get explicit confirmation before each real-quota run.
2. Verify: every complaint has a cluster member row; cohorts + `cohort_event_links` exist; record counts per table.
3. `python -m backtrace_eval.ablation --run-id dev-run-3` → report.
4. **Decision:** if C is not clearly better than B on false-merge rate and homogeneity, record "narrative shifts emphasis to T1 (misattribution)" in design doc §13.3 / Change Log; otherwise "T2 holds on dev". Write the numbers and date either way.
5. Backend tests, frontend lint/build, `git diff --check`, import-rule test; update this plan's Status block; commit in focused chunks.

**Done when:** the §19 Day 3 criterion is shown on `dev-run-3`: cohorts + links in DB, first ablation report, T2-vs-T1 decision recorded.

## Known risks

- `dev` event scopes are region-only, and non-network causes (billing double charge, price increase) can share a region and time window with a network event. Without topology `scope_match` these are the §5.7 false-merge case; the ablation's false-merge rate is exactly what measures it. Do not "fix" it by tuning weights against gold labels.
- Root causes with no event record (§5.4) can only surface as `no_linked_evidence` cohorts — expected, not a bug.
- HDBSCAN `min_cluster_size=15` on ~1,600 complaints is a guess; if almost everything is noise on `dev-run-3`, change it **once**, in config, with the reason written next to it.
- Re-extraction of `dev-run-3` (~1,600 `generate_content` calls) competes with the same 500/day quota as the text regen — the schedule slip is quota-bound, not code-bound. Consider batching (Day 3 prep #2) before Task 8.
