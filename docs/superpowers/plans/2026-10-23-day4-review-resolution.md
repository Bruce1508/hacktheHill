# Day 4 — Review → Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Compact plan (by choice, 2026-10-23, following Day 3's convention):** architecture, interfaces, config values and test assertions are fixed here; implementers write the code. Every task is TDD: write the listed tests → see them fail → implement → see them pass → commit.

**Goal:** Meet the Day 4 row of `Backtrace — Technical Design Doc.md` §19: demo steps 1–9 (scatter → cohorts → evidence → confirm → remedy → letter → gate → approve) work end to end through the UI on the `dev` dataset, with dev auth (§12).

**Architecture:** Each new backend capability is a **pure core** (plain Python/dataclasses in → plain data out, unit-tested with no DB/network) plus a thin DB- or API-facing wrapper, matching Day 3's `run_<x>_stage` pattern (`backend/src/backtrace/pipeline/layout.py` is the reference). The remedy engine and Consistency Gate rules never read `eval` schema or call an LLM for the amount — only letter drafting and the Gate's "every issue addressed" check use Gemini, and only after the rules pass. The frontend is additive: new routes/components beside the existing Day 1–2 scatter page, reusing `apps/web/src/lib/api.ts` and `src/components/ui/`.

**Tech Stack:** FastAPI + Pydantic (existing), SQLAlchemy 2.x + Alembic (existing), Next.js 16 App Router + shadcn/ui + Tailwind (existing), **ECharts (new frontend dependency — not yet installed)** for the evidence-view timeline, Gemini structured output via `google-genai` `interactions.create` (same pattern as `GeminiExtractionProvider`).

**Spec:** `Backtrace — Technical Design Doc.md` §6.4–6.5 (layout, API surface), §7.1 (schema), §8.2 steps 8 & 10–11, §8.3 (evidence linking, already built), §9.2 (vector-only is Day 5+, **not needed here**), §10 (remedy engine, letter drafting, Consistency Gate), §11 (worker/jobs), §12 (auth/audit). Predecessor: `docs/superpowers/plans/2026-10-17-day3-root-cause.md`.

## Global Constraints

- `backtrace` must never import `backtrace_eval` (`backend/tests/test_import_rules.py` enforces it). The remedy engine must not read `configs/worlds/*.yaml` (that's `backtrace_eval`'s world-generation config) — pricing lives in the `remedy_policies` row itself (§10.1: "Rules are versioned; every remedy stores the version used").
- The pipeline (`bt_pipeline` role) never reads the `eval` schema. No remedy amount, Gate threshold, or policy value is tuned against gold labels.
- A cohort gets **one formula**, but the amount is computed per member (§10.1) — outage hours differ by node.
- Vulnerable customer (`vulnerability_signals[]` non-empty) → always routed to individual review, never an automatic cohort remedy (§10.1, §10.3).
- Rules run before the LLM in the Gate; a draft that fails a rule spends no LLM tokens (§10.3).
- Every write action is audited: `user_id`, role, `auth_mode`, action, target, before/after state, hash-chained (§12, §7.1 `audit_log`).
- Each stage/endpoint is idempotent per `run_id`/`cohort_id`: re-running replaces, never duplicates (Day 3's established pattern).
- Dev auth only (`AUTH_MODE=dev`, existing `backend/src/backtrace/api/auth.py::current_user`) — Auth0 is explicitly Day 6, out of scope here.
- **Known gap, flagged not silently fixed:** `backend/src/backtrace/contracts/evidence.py::EvidencePackStub`'s docstring says it should be "filled in... once evidence linking exists — Day 3 work," but Day 3's plan explicitly listed "Gemini hypothesis (§8.2 step 8)" as out of scope. Demo step 4 needs a cited hypothesis, so Task 3 of this plan builds it now — one day later than the stub's comment expected, not silently dropped.

## File structure

| File | Responsibility |
| --- | --- |
| `backend/alembic/versions/0006_remedy_review_tables.py` | `remedy_policies`, `remedies`, `letters`, `approvals`, `audit_log` tables + seed rows for `remedy_policies` |
| `backend/src/backtrace/db/models.py` | add ORM models: `RemedyPolicy`, `Remedy`, `Letter`, `Approval`, `AuditLog` |
| `backend/src/backtrace/llm/config.py` | add `ModelPin` sections for `hypothesis` and `letter_drafting`; add `GateConfig` (forbidden phrases) |
| `configs/pipeline.yaml` | new `hypothesis`, `letter_drafting`, `gate` sections |
| `backend/src/backtrace/audit.py` | `append_audit(session, actor, action, target_type, target_id, before, after) -> AuditLog` — hash chain |
| `backend/src/backtrace/contracts/evidence.py` | replace `EvidencePackStub` with real `EvidencePack` + `CohortEvidenceOut`, `CohortOut`, `CohortListOut` |
| `backend/src/backtrace/contracts/remedy.py` | `RemedyOut`, `LetterOut`, `ApprovalOut`, `GateResultOut` |
| `backend/src/backtrace/pipeline/hypothesis.py` | evidence-pack builder + `run_hypothesis_stage(session_factory, run_id, provider) -> dict` (Gemini call, citation validator) |
| `backend/src/backtrace/remedy/policy.py` | pure policy-application functions (no DB): `apply_policy(policy, member_facts) -> RemedyComputation` |
| `backend/src/backtrace/remedy/engine.py` | `compute_cohort_remedies(session_factory, cohort_id) -> dict` — loads cohort + members + policy, calls `policy.apply_policy`, writes `remedies` |
| `backend/src/backtrace/remedy/draft.py` | `draft_letter(session_factory, remedy_id, provider) -> dict` — Gemini letter drafting, writes `letters` |
| `backend/src/backtrace/gate/rules.py` | pure rule checks (no DB, no LLM): `check_amount`, `check_forbidden_phrases`, `check_vulnerability`, `check_cohort_consistency` |
| `backend/src/backtrace/gate/consistency.py` | `run_gate(session_factory, letter_id, provider) -> dict` — runs rules, then the one LLM check, writes `letters.gate_result` |
| `backend/src/backtrace/api/cohorts.py` | new router: `GET /cohorts`, `GET /cohorts/{id}`, `GET /cohorts/{id}/evidence`, `POST /cohorts/{id}/confirm|split|merge`, `POST /cohorts/{id}/remedy` |
| `backend/src/backtrace/api/remedies.py` | new router: `POST /remedies/{id}/drafts`, `POST /remedies/{id}/gate`, `POST /remedies/{id}/approve` |
| `backend/src/backtrace/api/main.py` | `app.include_router(cohorts.router)`, `app.include_router(remedies.router)` |
| `apps/web/package.json` | add `echarts` + `echarts-for-react` |
| `apps/web/src/lib/api.ts` | add typed fetchers for the new endpoints |
| `apps/web/src/app/cohorts/page.tsx` | cohort list (demo steps 2–3) |
| `apps/web/src/app/cohorts/[id]/page.tsx` | cohort detail: evidence view, confirm/split/merge, remedy/letter/gate/approve panel (demo steps 4–9) |
| `apps/web/src/components/evidence-timeline.tsx` | ECharts timeline: complaint burst × telemetry anomaly |
| `apps/web/src/components/demo-user-switcher.tsx` | dev-auth role switcher (sets `X-Demo-User` via cookie) |
| `apps/web/src/components/ui/dialog.tsx`, `badge.tsx`, `select.tsx` | shadcn components needed by confirm/split/merge and the role switcher |

---

### Task 1: Remedy/review tables + ORM models

**Files:**
- Create: `backend/alembic/versions/0006_remedy_review_tables.py`
- Modify: `backend/src/backtrace/db/models.py`
- Test: `backend/tests/test_models_remedy.py`

**Interfaces:**
- Produces: ORM classes `RemedyPolicy(id, rule_type, config, version, created_at)`, `Remedy(id, cohort_id, complaint_id, amount, policy_rule_id, policy_version, rationale, created_at)`, `Letter(id, remedy_id, complaint_id, draft, prompt_version, gate_result, created_at)`, `Approval(id, remedy_id, approver_user_id, role, auth_mode, mfa_used, decision, decided_at)`, `AuditLog(id, actor_user_id, role, auth_mode, action, target_type, target_id, before, after, prev_hash, hash, created_at)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models_remedy.py
import datetime as dt
from decimal import Decimal

from backtrace.db.models import Approval, AuditLog, Cohort, Complaint, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session


def test_remedy_review_tables_round_trip(database_url_pipeline):
    with get_session(database_url_pipeline) as session:
        session.merge(PipelineRun(run_id="test-remedy-models", dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="test-remedy-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="test-remedy-complaint", customer_id="test-remedy-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id="test-remedy-cohort", run_id="test-remedy-models", status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.commit()

        session.merge(Remedy(id="remedy-1", cohort_id="test-remedy-cohort", complaint_id="test-remedy-complaint", amount=Decimal("3.50"), policy_rule_id="policy-outage-v1", policy_version=1, rationale="outage credit"))
        session.commit()

        session.merge(Letter(id="letter-1", remedy_id="remedy-1", complaint_id="test-remedy-complaint", draft="Dear customer...", prompt_version="letter-v1", gate_result=None))
        session.commit()

        session.merge(Approval(id="approval-1", remedy_id="remedy-1", approver_user_id="demo-team-lead", role="team_lead", auth_mode="dev", mfa_used=False, decision="approved", decided_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(AuditLog(actor_user_id="demo-team-lead", role="team_lead", auth_mode="dev", action="remedy.approve", target_type="remedy", target_id="remedy-1", before={}, after={"decision": "approved"}, prev_hash=None, hash="x" * 64))
        session.commit()

        assert session.get(Remedy, "remedy-1").amount == Decimal("3.50")
        assert session.get(Letter, "letter-1").gate_result is None
        assert session.get(Approval, "approval-1").decision == "approved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace PYTHONPATH=src .venv/bin/python -m pytest tests/test_models_remedy.py -v`
Expected: FAIL with `ImportError: cannot import name 'RemedyPolicy'` (models don't exist yet)

- [ ] **Step 3: Write the migration**

```python
# backend/alembic/versions/0006_remedy_review_tables.py
"""Day 4 remedy/review tables (§7.1): remedy_policies, remedies, letters,
approvals, audit_log."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.create_table(
        "remedy_policies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("rule_type", sa.String, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="app",
    )
    op.create_table(
        "remedies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("cohort_id", sa.String, sa.ForeignKey("app.cohorts.id"), nullable=False),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), nullable=False),
        sa.Column("amount", sa.Numeric, nullable=False),
        sa.Column("policy_rule_id", sa.String, sa.ForeignKey("app.remedy_policies.id"), nullable=False),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("rationale", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="app",
    )
    op.create_table(
        "letters",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("remedy_id", sa.String, sa.ForeignKey("app.remedies.id"), nullable=False),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), nullable=False),
        sa.Column("draft", sa.String, nullable=False),
        sa.Column("prompt_version", sa.String, nullable=False),
        sa.Column("gate_result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="app",
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("remedy_id", sa.String, sa.ForeignKey("app.remedies.id"), nullable=False),
        sa.Column("approver_user_id", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("auth_mode", sa.String, nullable=False),
        sa.Column("mfa_used", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("auth_mode", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("target_type", sa.String, nullable=False),
        sa.Column("target_id", sa.String, nullable=False),
        sa.Column("before", sa.JSON, nullable=False),
        sa.Column("after", sa.JSON, nullable=False),
        sa.Column("prev_hash", sa.String, nullable=True),
        sa.Column("hash", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="app",
    )
    op.execute(
        """
        INSERT INTO app.remedy_policies (id, rule_type, config, version) VALUES
        ('policy-outage-credit-v1', 'outage_credit', '{"price_table": {"fiber_basic": 2.00, "fiber_pro": 3.50, "tv_bundle": 4.75, "business_ethernet": 12.00}}', 1),
        ('policy-overcharge-refund-v1', 'overcharge_refund', '{"goodwill_amount": 15.00}', 1)
        """
    )


def downgrade() -> None:
    op.drop_table("audit_log", schema="app")
    op.drop_table("approvals", schema="app")
    op.drop_table("letters", schema="app")
    op.drop_table("remedies", schema="app")
    op.drop_table("remedy_policies", schema="app")
```

- [ ] **Step 4: Add the ORM models**

```python
# backend/src/backtrace/db/models.py — append
class RemedyPolicy(Base):
    __tablename__ = "remedy_policies"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    rule_type: Mapped[str]  # "outage_credit" | "overcharge_refund"
    config: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int]


class Remedy(Base):
    __tablename__ = "remedies"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("app.cohorts.id"))
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric)
    policy_rule_id: Mapped[str] = mapped_column(ForeignKey("app.remedy_policies.id"))
    policy_version: Mapped[int]
    rationale: Mapped[str]


class Letter(Base):
    __tablename__ = "letters"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    remedy_id: Mapped[str] = mapped_column(ForeignKey("app.remedies.id"))
    complaint_id: Mapped[str] = mapped_column(ForeignKey("app.complaints.complaint_id"))
    draft: Mapped[str]
    prompt_version: Mapped[str]
    gate_result: Mapped[dict | None] = mapped_column(JSON, default=None)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = {"schema": "app"}

    id: Mapped[str] = mapped_column(primary_key=True)
    remedy_id: Mapped[str] = mapped_column(ForeignKey("app.remedies.id"))
    approver_user_id: Mapped[str]
    role: Mapped[str]
    auth_mode: Mapped[str]
    mfa_used: Mapped[bool] = mapped_column(default=False)
    decision: Mapped[str]  # "approved" | "rejected"
    decided_at: Mapped[dt.datetime]


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str]
    role: Mapped[str]
    auth_mode: Mapped[str]
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str | None] = mapped_column(default=None)
    hash: Mapped[str]
```

(Add `from decimal import Decimal` and `Numeric` to the existing imports at the top of `models.py` if not already present — confirm with `grep -n "^from\|^import" backend/src/backtrace/db/models.py` first.)

- [ ] **Step 5: Run migration and test**

Run: `cd backend && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace .venv/bin/alembic upgrade head && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace PYTHONPATH=src .venv/bin/python -m pytest tests/test_models_remedy.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0006_remedy_review_tables.py backend/src/backtrace/db/models.py backend/tests/test_models_remedy.py
git commit -m "feat(db): Day 4 remedy/review tables (remedy_policies, remedies, letters, approvals, audit_log)"
```

---

### Task 2: Audit log with hash chain

**Files:**
- Create: `backend/src/backtrace/audit.py`
- Test: `backend/tests/test_audit.py`

**Interfaces:**
- Consumes: `AuditLog` ORM model (Task 1).
- Produces: `append_audit(session: Session, actor_user_id: str, role: str, auth_mode: str, action: str, target_type: str, target_id: str, before: dict, after: dict) -> AuditLog` — every later task that mutates cohort/remedy/letter/approval state calls this inside the same transaction as its own write.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_audit.py
import hashlib
import json

from backtrace.audit import append_audit
from backtrace.db.models import AuditLog
from backtrace.db.session import get_session


def test_hash_chains_to_previous_row(database_url_pipeline):
    with get_session(database_url_pipeline) as session:
        session.query(AuditLog).delete()
        session.commit()

        first = append_audit(session, "demo-agent", "agent", "dev", "cohort.view", "cohort", "c1", before={}, after={})
        second = append_audit(session, "demo-team-lead", "team_lead", "dev", "cohort.confirm", "cohort", "c1", before={"status": "proposed"}, after={"status": "confirmed"})

        assert first.prev_hash is None
        assert second.prev_hash == first.hash
        expected = hashlib.sha256(
            json.dumps(
                {"prev_hash": first.hash, "actor_user_id": "demo-team-lead", "role": "team_lead", "auth_mode": "dev", "action": "cohort.confirm", "target_type": "cohort", "target_id": "c1", "before": {"status": "proposed"}, "after": {"status": "confirmed"}},
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert second.hash == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace PYTHONPATH=src .venv/bin/python -m pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtrace.audit'`

- [ ] **Step 3: Implement**

```python
# backend/src/backtrace/audit.py
"""Append-only audit log with a hash chain (§7.1, §12): each row hashes the
previous row's hash plus its own fields, so tampering with any row breaks
every hash after it."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backtrace.db.models import AuditLog


def _last_hash(session: Session) -> str | None:
    row = session.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    return row


def append_audit(
    session: Session,
    actor_user_id: str,
    role: str,
    auth_mode: str,
    action: str,
    target_type: str,
    target_id: str,
    before: dict,
    after: dict,
) -> AuditLog:
    prev_hash = _last_hash(session)
    payload = {
        "prev_hash": prev_hash, "actor_user_id": actor_user_id, "role": role, "auth_mode": auth_mode,
        "action": action, "target_type": target_type, "target_id": target_id, "before": before, "after": after,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    row = AuditLog(
        actor_user_id=actor_user_id, role=role, auth_mode=auth_mode, action=action,
        target_type=target_type, target_id=target_id, before=before, after=after,
        prev_hash=prev_hash, hash=digest,
    )
    session.add(row)
    session.flush()
    return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtrace/audit.py backend/tests/test_audit.py
git commit -m "feat(audit): hash-chained audit log helper (§12)"
```

---

### Task 3: Real evidence pack + hypothesis stage

**Files:**
- Modify: `backend/src/backtrace/contracts/evidence.py` (replace `EvidencePackStub`)
- Create: `backend/src/backtrace/pipeline/hypothesis.py`
- Modify: `backend/src/backtrace/llm/config.py` (add `hypothesis: ModelPin`), `configs/pipeline.yaml` (add `hypothesis:` section), `backend/src/backtrace/worker/main.py` (add `"hypothesis"` to the `pipeline.run` stage tuple, after `"linking"` and before `"layout"`)
- Test: `backend/tests/test_pipeline_hypothesis.py`

**Interfaces:**
- Consumes: `Cohort`, `CohortMember`, `CohortEventLink`, `Complaint`, `Event`, `DetectedAnomaly` (existing models); `GeminiExtractionProvider`-style structured-output call pattern (`backend/src/backtrace/llm/providers.py:107-135`).
- Produces: `EvidencePack(cohort_id, complaint_ids, event_ids, anomaly_ids, score_components, sample_complaint_texts)` (replaces `EvidencePackStub`); `HypothesisOutput(text: str, cited_complaint_ids: list[str], cited_event_ids: list[str], cited_anomaly_ids: list[str])` (new, in `evidence.py`); `run_hypothesis_stage(session_factory, run_id, provider) -> dict` — writes `Cohort.hypothesis`/`hypothesis_citations`/`confidence`. Later tasks (Task 4's `/cohorts/{id}/evidence`) read `Cohort.hypothesis`/`hypothesis_citations` directly.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pipeline_hypothesis.py
import datetime as dt

from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, Customer, DetectedAnomaly, PipelineRun
from backtrace.db.session import get_session, make_session_factory
from backtrace.pipeline.hypothesis import FakeHypothesisProvider, build_evidence_pack, run_hypothesis_stage

RUN_ID = "test-hypothesis-run"
COHORT_ID = "test-hypothesis-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="hyp-cust", region="north", plan="fiber_pro", segment="residential", node_id="hyp-node"))
        session.merge(Complaint(complaint_id="hyp-complaint-1", customer_id="hyp-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="internet is down", product="fiber_pro", region="north", node_id="hyp-node"))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked"))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="hyp-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="hyp-anomaly-1", run_id=RUN_ID, node_id="hyp-node", metric="packet_loss_pct", start_at=dt.datetime.now(dt.timezone.utc), end_at=dt.datetime.now(dt.timezone.utc), peak_score=9.0, method="rolling_z_v1"))
        session.merge(CohortEventLink(cohort_id=COHORT_ID, run_id=RUN_ID, anomaly_id="hyp-anomaly-1", overlap_score=5.0, evidence={"telemetry": 1.0}))
        session.commit()


def test_build_evidence_pack_includes_real_ids(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    with session_factory() as session:
        pack = build_evidence_pack(session, COHORT_ID)
    assert pack.cohort_id == COHORT_ID
    assert pack.complaint_ids == ["hyp-complaint-1"]
    assert pack.anomaly_ids == ["hyp-anomaly-1"]


def test_run_hypothesis_stage_rejects_uncited_ids(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeHypothesisProvider(fake_cited_complaint_ids=["not-a-real-id"])
    result = run_hypothesis_stage(session_factory, RUN_ID, provider)
    assert result["rejected"] == 1
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.hypothesis is None  # invalid citation -> not shown (§8.2 step 8)


def test_run_hypothesis_stage_accepts_valid_citations(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeHypothesisProvider(fake_cited_complaint_ids=["hyp-complaint-1"], fake_cited_anomaly_ids=["hyp-anomaly-1"])
    result = run_hypothesis_stage(session_factory, RUN_ID, provider)
    assert result["accepted"] == 1
    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.hypothesis is not None
        assert cohort.hypothesis_citations["complaint_ids"] == ["hyp-complaint-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=postgresql+psycopg://bt_pipeline:devpassword@localhost:5433/backtrace PYTHONPATH=src .venv/bin/python -m pytest tests/test_pipeline_hypothesis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtrace.pipeline.hypothesis'`

- [ ] **Step 3: Replace the evidence contract stub**

```python
# backend/src/backtrace/contracts/evidence.py
from pydantic import BaseModel


class EvidencePack(BaseModel):
    """Real evidence pack for the hypothesis call and the /cohorts/{id}/evidence
    response (§8.2 step 8, §8.3). Replaces EvidencePackStub now that evidence
    linking (Day 3) exists."""

    cohort_id: str
    complaint_ids: list[str]
    event_ids: list[str]
    anomaly_ids: list[str]
    score_components: dict[str, float]  # averaged across cohort_event_links.evidence
    sample_complaint_texts: list[str]  # pii-redacted, capped (see hypothesis.py)


class HypothesisOutput(BaseModel):
    text: str
    cited_complaint_ids: list[str] = []
    cited_event_ids: list[str] = []
    cited_anomaly_ids: list[str] = []


class CohortOut(BaseModel):
    id: str
    run_id: str
    status: str
    kind: str
    hypothesis: str | None
    confidence: float | None
    member_count: int

    model_config = {"from_attributes": True}


class CohortListOut(BaseModel):
    cohorts: list[CohortOut]


class CohortEvidenceOut(BaseModel):
    cohort_id: str
    score_components: dict[str, float]
    hypothesis: str | None
    hypothesis_citations: dict | None
    linked_event_ids: list[str]
    linked_anomaly_ids: list[str]
    sample_complaint_ids: list[str]
```

- [ ] **Step 4: Add the `hypothesis` config section**

```yaml
# configs/pipeline.yaml — add after the embedding section
hypothesis:
  model_id: gemini-flash-lite-latest
  prompt_version: hypothesis-v1
```

```python
# backend/src/backtrace/llm/config.py — add to PipelineConfig
hypothesis: ModelPin
# ...and in PipelineConfig.load():
hypothesis=ModelPin(**raw["hypothesis"]),
```

- [ ] **Step 5: Implement the hypothesis stage**

```python
# backend/src/backtrace/pipeline/hypothesis.py
"""Gemini hypothesis generation over a real evidence pack (§8.2 step 8).
A hypothesis that cites an id not present in its own pack is rejected
outright — citations are the only thing standing between a plausible-
sounding guess and a claim a reviewer can actually check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backtrace.contracts.evidence import EvidencePack, HypothesisOutput
from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, DetectedAnomaly, Event

SAMPLE_COMPLAINT_CAP = 5


class HypothesisProvider(Protocol):
    model_id: str
    prompt_version: str

    def generate(self, pack: EvidencePack) -> HypothesisOutput: ...


@dataclass
class FakeHypothesisProvider:
    """Deterministic test double — set fake_cited_* to test the citation
    validator without a real Gemini call."""

    model_id: str = "fake-hypothesis-v1"
    prompt_version: str = "hypothesis-v1"
    fake_cited_complaint_ids: list[str] | None = None
    fake_cited_event_ids: list[str] | None = None
    fake_cited_anomaly_ids: list[str] | None = None

    def generate(self, pack: EvidencePack) -> HypothesisOutput:
        return HypothesisOutput(
            text="Fake hypothesis for testing.",
            cited_complaint_ids=self.fake_cited_complaint_ids or [],
            cited_event_ids=self.fake_cited_event_ids or [],
            cited_anomaly_ids=self.fake_cited_anomaly_ids or [],
        )


def build_evidence_pack(session: Session, cohort_id: str) -> EvidencePack:
    cohort = session.get(Cohort, cohort_id)
    complaint_ids = [
        row[0] for row in session.execute(
            select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id)
        )
    ]
    links = session.execute(select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id)).scalars().all()
    event_ids = sorted({link.event_id for link in links if link.event_id})
    anomaly_ids = sorted({link.anomaly_id for link in links if link.anomaly_id})

    totals: dict[str, float] = {}
    for link in links:
        for key, value in link.evidence.items():
            totals[key] = totals.get(key, 0.0) + value
    score_components = {k: v / len(links) for k, v in totals.items()} if links else {}

    sample_texts = [
        row[0] for row in session.execute(
            select(Complaint.text).where(Complaint.complaint_id.in_(complaint_ids)).limit(SAMPLE_COMPLAINT_CAP)
        )
    ]
    return EvidencePack(
        cohort_id=cohort_id, complaint_ids=sorted(complaint_ids), event_ids=event_ids, anomaly_ids=anomaly_ids,
        score_components=score_components, sample_complaint_texts=sample_texts,
    )


def _validate_citations(pack: EvidencePack, output: HypothesisOutput) -> bool:
    return (
        set(output.cited_complaint_ids) <= set(pack.complaint_ids)
        and set(output.cited_event_ids) <= set(pack.event_ids)
        and set(output.cited_anomaly_ids) <= set(pack.anomaly_ids)
    )


def run_hypothesis_stage(session_factory: sessionmaker, run_id: str, provider: HypothesisProvider) -> dict:
    with session_factory() as session:
        cohort_ids = [row[0] for row in session.execute(select(Cohort.id).where(Cohort.run_id == run_id))]

    accepted = rejected = 0
    for cohort_id in cohort_ids:
        with session_factory() as session:
            pack = build_evidence_pack(session, cohort_id)
            if not pack.complaint_ids:
                continue
            output = provider.generate(pack)
            if not _validate_citations(pack, output):
                rejected += 1
                continue
            accepted += 1
            cohort = session.get(Cohort, cohort_id)
            cohort.hypothesis = output.text
            cohort.hypothesis_citations = {
                "complaint_ids": output.cited_complaint_ids,
                "event_ids": output.cited_event_ids,
                "anomaly_ids": output.cited_anomaly_ids,
            }
            cohort.confidence = len(output.cited_complaint_ids + output.cited_event_ids + output.cited_anomaly_ids) / max(
                1, len(pack.complaint_ids) + len(pack.event_ids) + len(pack.anomaly_ids)
            )
            session.commit()
    return {"accepted": accepted, "rejected": rejected}
```

- [ ] **Step 6: Add a real `GeminiHypothesisProvider`**

```python
# backend/src/backtrace/llm/providers.py — append
class GeminiHypothesisProvider:
    """Same interactions.create structured-output pattern as
    GeminiExtractionProvider (lines 107-135 of this file)."""

    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def generate(self, pack):
        from backtrace.contracts.evidence import HypothesisOutput
        from backtrace.llm.prompts import HYPOTHESIS_PROMPT_V1

        prompt = HYPOTHESIS_PROMPT_V1.format(
            complaint_ids=pack.complaint_ids, event_ids=pack.event_ids, anomaly_ids=pack.anomaly_ids,
            score_components=pack.score_components, sample_texts=pack.sample_complaint_texts,
        )
        resp = self._client.interactions.create(
            model=self.model_id, input=prompt,
            response_format={"type": "text", "mime_type": "application/json", "schema": HypothesisOutput.model_json_schema()},
        )
        return HypothesisOutput.model_validate_json(resp.output_text)
```

Add `HYPOTHESIS_PROMPT_V1` to `backend/src/backtrace/llm/prompts.py` next to the existing `EXTRACTION_PROMPT_V1`/`DEV_TEXT_PROMPT_V1`, instructing the model to cite only ids from the pack and to write "no citable evidence" as the hypothesis if it cannot.

- [ ] **Step 7: Wire the stage into the worker**

```python
# backend/src/backtrace/worker/main.py — modify _run_job's stage tuple
stages = ("extraction", "embedding", "anomaly", "burst", "clustering", "linking", "hypothesis", "layout") if job.type == "pipeline.run" else (job.stage,)
# ...and add the dispatch branch:
elif stage == "hypothesis":
    result = run_hypothesis_stage(session_factory, job.run_id, hypothesis_provider)
```

`_build_providers` and `_run_job`'s signature need a `hypothesis_provider` argument threaded through from `run_forever`, built the same way as `extraction_provider`/`embedding_provider` (fake vs. `GeminiHypothesisProvider` based on `use_fake_providers`).

- [ ] **Step 8: Run tests to verify they pass**

Run: same as Step 2. Expected: PASS (all three tests)

- [ ] **Step 9: Run full suite + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... DATABASE_URL_EVAL=... AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass (no regressions in Day 1-3 tests)

```bash
git add backend/src/backtrace/contracts/evidence.py backend/src/backtrace/pipeline/hypothesis.py backend/src/backtrace/llm/config.py backend/src/backtrace/llm/providers.py backend/src/backtrace/llm/prompts.py backend/src/backtrace/worker/main.py configs/pipeline.yaml backend/tests/test_pipeline_hypothesis.py
git commit -m "feat(pipeline): hypothesis generation with citation validation (§8.2 step 8)"
```

---

### Task 4: Cohort list/detail/evidence endpoints

**Files:**
- Create: `backend/src/backtrace/api/cohorts.py`
- Modify: `backend/src/backtrace/api/main.py` (mount router)
- Test: `backend/tests/test_api_cohorts.py`

**Interfaces:**
- Consumes: `CohortOut`, `CohortListOut`, `CohortEvidenceOut` (Task 3); `build_evidence_pack` (Task 3); `current_user` (existing `api/auth.py`).
- Produces: `GET /cohorts`, `GET /cohorts/{id}`, `GET /cohorts/{id}/evidence` — frontend Task 10/11 call these by path.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_cohorts.py
import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Cohort, CohortMember, Complaint, Customer, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-api-cohorts-run"
COHORT_ID = "test-api-cohorts-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="api-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="api-complaint-1", customer_id="api-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked", hypothesis="test hypothesis", confidence=0.8))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="api-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.commit()


def test_list_and_get_cohort(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)
    headers = {"X-Demo-User": "demo-agent"}

    listed = client.get("/cohorts", headers=headers, params={"run_id": RUN_ID})
    assert listed.status_code == 200
    assert any(c["id"] == COHORT_ID for c in listed.json()["cohorts"])

    detail = client.get(f"/cohorts/{COHORT_ID}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["hypothesis"] == "test hypothesis"

    evidence = client.get(f"/cohorts/{COHORT_ID}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()["sample_complaint_ids"] == ["api-complaint-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_cohorts.py -v`
Expected: FAIL (404 — router not mounted / module missing)

- [ ] **Step 3: Implement the router**

```python
# backend/src/backtrace/api/cohorts.py
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from backtrace.api.auth import CurrentUser, current_user
from backtrace.contracts.evidence import CohortEvidenceOut, CohortListOut, CohortOut
from backtrace.db.models import Cohort, CohortMember
from backtrace.db.session import get_session
from backtrace.pipeline.hypothesis import build_evidence_pack

router = APIRouter()


def _cohort_out(session, cohort: Cohort) -> CohortOut:
    member_count = session.execute(select(func.count()).where(CohortMember.cohort_id == cohort.id)).scalar_one()
    return CohortOut(id=cohort.id, run_id=cohort.run_id, status=cohort.status, kind=cohort.kind, hypothesis=cohort.hypothesis, confidence=cohort.confidence, member_count=member_count)


@router.get("/cohorts")
def list_cohorts(_user: Annotated[CurrentUser, Depends(current_user)], run_id: Annotated[str, Query()]) -> CohortListOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohorts = session.execute(select(Cohort).where(Cohort.run_id == run_id)).scalars().all()
        return CohortListOut(cohorts=[_cohort_out(session, c) for c in cohorts])


@router.get("/cohorts/{cohort_id}")
def get_cohort(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        return _cohort_out(session, cohort)


@router.get("/cohorts/{cohort_id}/evidence")
def get_cohort_evidence(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortEvidenceOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        pack = build_evidence_pack(session, cohort_id)
        return CohortEvidenceOut(
            cohort_id=cohort_id, score_components=pack.score_components, hypothesis=cohort.hypothesis,
            hypothesis_citations=cohort.hypothesis_citations, linked_event_ids=pack.event_ids,
            linked_anomaly_ids=pack.anomaly_ids, sample_complaint_ids=pack.complaint_ids[:5],
        )
```

```python
# backend/src/backtrace/api/main.py — add near the top, after existing imports
from backtrace.api import cohorts
...
app.include_router(cohorts.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtrace/api/cohorts.py backend/src/backtrace/api/main.py backend/tests/test_api_cohorts.py
git commit -m "feat(api): cohort list/detail/evidence endpoints (demo steps 2-4)"
```

---

### Task 5: Confirm / split / merge (human review, audited)

**Files:**
- Modify: `backend/src/backtrace/api/cohorts.py` (add 3 endpoints)
- Test: `backend/tests/test_api_cohorts_review.py`

**Interfaces:**
- Consumes: `append_audit` (Task 2); `current_user` role (`agent` cannot confirm — only `team_lead`/`compliance` per §12's role table extended to cohort actions, since confirm/split/merge are review actions, not plain remedy approval; this plan treats "confirm/split/merge" as the `team_lead` tier, consistent with §12's "`team_lead` can confirm/split/merge cohorts").
- Produces: `POST /cohorts/{id}/confirm`, `POST /cohorts/{id}/split`, `POST /cohorts/{id}/merge`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_cohorts_review.py
import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import AuditLog, Cohort, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-review-run"
COHORT_ID = "test-review-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="proposed", kind="linked"))
        session.commit()


def test_agent_cannot_confirm_but_team_lead_can(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)

    denied = client.post(f"/cohorts/{COHORT_ID}/confirm", headers={"X-Demo-User": "demo-agent"})
    assert denied.status_code == 403

    allowed = client.post(f"/cohorts/{COHORT_ID}/confirm", headers={"X-Demo-User": "demo-team-lead"})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "confirmed"

    with get_session(database_url_pipeline) as session:
        cohort = session.get(Cohort, COHORT_ID)
        assert cohort.status == "confirmed"
        last_audit = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert last_audit.action == "cohort.confirm"
        assert last_audit.target_id == COHORT_ID
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_cohorts_review.py -v`
Expected: FAIL with 404 (endpoint doesn't exist)

- [ ] **Step 3: Implement**

```python
# backend/src/backtrace/api/cohorts.py — append
from fastapi import HTTPException, status as http_status

from backtrace.audit import append_audit

REVIEW_ROLES = {"team_lead", "compliance"}


def _require_review_role(user: CurrentUser) -> None:
    if user.role not in REVIEW_ROLES:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires team_lead or compliance")


@router.post("/cohorts/{cohort_id}/confirm")
def confirm_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "confirmed"
        append_audit(session, user.user_id, user.role, "dev", "cohort.confirm", "cohort", cohort_id, before=before, after={"status": "confirmed"})
        session.commit()
        return _cohort_out(session, cohort)


@router.post("/cohorts/{cohort_id}/split")
def split_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "split"
        append_audit(session, user.user_id, user.role, "dev", "cohort.split", "cohort", cohort_id, before=before, after={"status": "split"})
        session.commit()
        return _cohort_out(session, cohort)


@router.post("/cohorts/{cohort_id}/merge")
def merge_cohort(cohort_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> CohortOut:
    _require_review_role(user)
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")
        before = {"status": cohort.status}
        cohort.status = "merged"
        append_audit(session, user.user_id, user.role, "dev", "cohort.merge", "cohort", cohort_id, before=before, after={"status": "merged"})
        session.commit()
        return _cohort_out(session, cohort)
```

(Split/merge here only flip `status`; actually re-running linking for the affected cohorts, per §8.2 step 10's "Split/merge re-runs linking for the affected cohorts," is flagged out of scope for this task — it needs a design decision on which cohorts to re-link and isn't needed for demo steps 1–9, which only exercise `confirm`. Note this as a follow-up, don't silently build it.)

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/backtrace/api/cohorts.py backend/tests/test_api_cohorts_review.py
git commit -m "feat(api): cohort confirm/split/merge with role check + audit (demo step 5)"
```

---

### Task 6: Remedy engine (pure policy core + endpoint)

**Files:**
- Create: `backend/src/backtrace/remedy/__init__.py`, `backend/src/backtrace/remedy/policy.py`, `backend/src/backtrace/remedy/engine.py`
- Modify: `backend/src/backtrace/api/cohorts.py` (add `POST /cohorts/{id}/remedy`)
- Test: `backend/tests/test_remedy_policy.py`, `backend/tests/test_remedy_engine.py`

**Interfaces:**
- Consumes: `RemedyPolicy`, `Remedy`, `Cohort`, `CohortMember`, `Complaint`, `Customer` (Task 1 + existing); `ComplaintFeatures.extraction` (existing, for `vulnerability_signals[]`).
- Produces: `apply_policy(policy: RemedyPolicyFacts, member: MemberFacts) -> RemedyComputation` (pure); `compute_cohort_remedies(session_factory, cohort_id, policy_rule_id) -> dict` — writes `Remedy` rows, one per non-vulnerable member; vulnerable members are skipped and reported separately. Task 7 (letter drafting) reads `Remedy` rows by `cohort_id`.

- [ ] **Step 1: Write the failing test (pure policy)**

```python
# backend/tests/test_remedy_policy.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/test_remedy_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtrace.remedy'`

- [ ] **Step 3: Implement the pure policy core**

```python
# backend/src/backtrace/remedy/policy.py
"""Deterministic remedy rules (§10.1). Pure Python, no DB, no network —
unit-tested directly. A cohort gets one formula; the amount is computed
per member because outage hours (or overcharge amount) differ per member."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RemedyPolicyFacts:
    id: str
    rule_type: str  # "outage_credit" | "overcharge_refund"
    config: dict
    version: int


@dataclass(frozen=True)
class MemberFacts:
    complaint_id: str
    plan: str
    outage_hours: float | None
    overcharge_amount: Decimal | None
    vulnerability_signals: list[str]


@dataclass(frozen=True)
class RemedyComputation:
    complaint_id: str
    amount: Decimal
    policy_rule_id: str
    policy_version: int
    rationale: str


def apply_policy(policy: RemedyPolicyFacts, member: MemberFacts) -> RemedyComputation | None:
    if member.vulnerability_signals:  # §10.1, §10.3: always individual review
        return None

    if policy.rule_type == "outage_credit":
        if member.outage_hours is None:
            raise ValueError(f"outage_credit policy requires outage_hours for {member.complaint_id}")
        daily_price = Decimal(str(policy.config["price_table"][member.plan]))
        amount = (daily_price * Decimal(str(member.outage_hours)) / Decimal("24")).quantize(Decimal("0.01"))
        rationale = f"Outage credit: {member.outage_hours}h outage at ${daily_price}/day on {member.plan}."
    elif policy.rule_type == "overcharge_refund":
        if member.overcharge_amount is None:
            raise ValueError(f"overcharge_refund policy requires overcharge_amount for {member.complaint_id}")
        goodwill = Decimal(str(policy.config["goodwill_amount"]))
        amount = (member.overcharge_amount + goodwill).quantize(Decimal("0.01"))
        rationale = f"Overcharge refund: ${member.overcharge_amount} refunded plus ${goodwill} goodwill."
    else:
        raise ValueError(f"unknown rule_type {policy.rule_type!r}")

    return RemedyComputation(complaint_id=member.complaint_id, amount=amount, policy_rule_id=policy.id, policy_version=policy.version, rationale=rationale)
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Write the failing test (DB wrapper)**

```python
# backend/tests/test_remedy_engine.py
import datetime as dt

from backtrace.db.models import Cohort, CohortMember, Complaint, ComplaintFeatures, Customer, DetectedAnomaly, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.engine import compute_cohort_remedies

RUN_ID = "test-remedy-engine-run"
COHORT_ID = "test-remedy-engine-cohort"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="eng-cust-1", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Customer(id="eng-cust-2", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="eng-complaint-1", customer_id="eng-cust-1", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Complaint(complaint_id="eng-complaint-2", customer_id="eng-cust-2", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="eng-complaint-1", extraction={"vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="eng-complaint-2", extraction={"vulnerability_signals": ["hardship"]}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="eng-complaint-1", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(CohortMember(run_id=RUN_ID, complaint_id="eng-complaint-2", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="eng-anomaly-1", run_id=RUN_ID, node_id="n1", metric="packet_loss_pct", start_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), end_at=dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc), peak_score=9.0, method="rolling_z_v1"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.commit()


def test_compute_cohort_remedies_skips_vulnerable_member(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)

    result = compute_cohort_remedies(session_factory, COHORT_ID, "policy-outage-credit-v1")

    assert result["computed"] == 1
    assert result["routed_to_individual_review"] == 1
    with get_session(database_url_pipeline) as session:
        remedies = session.query(Remedy).filter(Remedy.cohort_id == COHORT_ID).all()
        assert len(remedies) == 1
        assert remedies[0].complaint_id == "eng-complaint-1"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=... PYTHONPATH=src .venv/bin/python -m pytest tests/test_remedy_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtrace.remedy.engine'`

- [ ] **Step 7: Implement the DB wrapper**

Outage hours come from the cohort's linked `DetectedAnomaly`/`Event` time window (`end_at - start_at`), matching §10.1's "linked event" input — using the anomaly with the highest `overlap_score` from `cohort_event_links` for that cohort.

```python
# backend/src/backtrace/remedy/engine.py
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, ComplaintFeatures, Customer, DetectedAnomaly, Event, Remedy, RemedyPolicy
from backtrace.remedy.policy import MemberFacts, RemedyPolicyFacts, apply_policy


def _cohort_outage_hours(session, cohort_id: str) -> float | None:
    link = session.execute(
        select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id).order_by(CohortEventLink.overlap_score.desc()).limit(1)
    ).scalar_one_or_none()
    if link is None:
        return None
    if link.anomaly_id:
        anomaly = session.get(DetectedAnomaly, link.anomaly_id)
        return (anomaly.end_at - anomaly.start_at).total_seconds() / 3600
    if link.event_id:
        event = session.get(Event, link.event_id)
        return (event.end_at - event.start_at).total_seconds() / 3600
    return None


def compute_cohort_remedies(session_factory: sessionmaker, cohort_id: str, policy_rule_id: str) -> dict:
    with session_factory() as session:
        cohort = session.get(Cohort, cohort_id)
        policy_row = session.get(RemedyPolicy, policy_rule_id)
        policy = RemedyPolicyFacts(id=policy_row.id, rule_type=policy_row.rule_type, config=policy_row.config, version=policy_row.version)
        outage_hours = _cohort_outage_hours(session, cohort_id) if policy.rule_type == "outage_credit" else None

        session.query(Remedy).filter(Remedy.cohort_id == cohort_id).delete()  # idempotent re-run

        computed = routed = 0
        member_rows = session.execute(select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id)).all()
        for (complaint_id,) in member_rows:
            complaint = session.get(Complaint, complaint_id)
            customer = session.get(Customer, complaint.customer_id)
            features = session.get(ComplaintFeatures, {"run_id": cohort.run_id, "complaint_id": complaint_id})
            vulnerability_signals = features.extraction.get("vulnerability_signals", []) if features else []

            member = MemberFacts(complaint_id=complaint_id, plan=customer.plan, outage_hours=outage_hours, overcharge_amount=None, vulnerability_signals=vulnerability_signals)
            result = apply_policy(policy, member)
            if result is None:
                routed += 1
                continue
            session.add(Remedy(id=f"{cohort_id}-{complaint_id}", cohort_id=cohort_id, complaint_id=complaint_id, amount=result.amount, policy_rule_id=result.policy_rule_id, policy_version=result.policy_version, rationale=result.rationale))
            computed += 1
        session.commit()
    return {"computed": computed, "routed_to_individual_review": routed}
```

- [ ] **Step 8: Run test to verify it passes**

Run: same as Step 6. Expected: PASS

- [ ] **Step 9: Add the endpoint**

```python
# backend/src/backtrace/api/cohorts.py — append
from backtrace.contracts.remedy import RemedyComputeOut
from backtrace.remedy.engine import compute_cohort_remedies
from backtrace.db.session import make_session_factory


@router.post("/cohorts/{cohort_id}/remedy")
def run_cohort_remedy(cohort_id: str, policy_rule_id: Annotated[str, Query()], user: Annotated[CurrentUser, Depends(current_user)]) -> RemedyComputeOut:
    _require_review_role(user)
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    result = compute_cohort_remedies(session_factory, cohort_id, policy_rule_id)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "cohort.remedy", "cohort", cohort_id, before={}, after=result)
        session.commit()
    return RemedyComputeOut(cohort_id=cohort_id, **result)
```

```python
# backend/src/backtrace/contracts/remedy.py — new file, start it here
from pydantic import BaseModel


class RemedyComputeOut(BaseModel):
    cohort_id: str
    computed: int
    routed_to_individual_review: int
```

- [ ] **Step 10: Run full suite + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... DATABASE_URL_EVAL=... AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass

```bash
git add backend/src/backtrace/remedy/ backend/src/backtrace/api/cohorts.py backend/src/backtrace/contracts/remedy.py backend/tests/test_remedy_policy.py backend/tests/test_remedy_engine.py
git commit -m "feat(remedy): deterministic remedy engine with vulnerability routing (§10.1, demo step 6)"
```

---

### Task 7: Letter drafting

**Files:**
- Create: `backend/src/backtrace/remedy/draft.py`
- Modify: `backend/src/backtrace/api/remedies.py` (new file), `backend/src/backtrace/api/main.py`, `backend/src/backtrace/llm/providers.py` (add `GeminiLetterProvider`), `backend/src/backtrace/llm/prompts.py` (add `LETTER_PROMPT_V1`), `configs/pipeline.yaml` (add `letter_drafting:` section)
- Test: `backend/tests/test_remedy_draft.py`

**Interfaces:**
- Consumes: `Remedy`, `Letter` (Task 1); `Complaint`, `ComplaintFeatures.extraction` (existing, for that customer's `issues[]`); `append_audit` (Task 2).
- Produces: `draft_letter(session_factory, remedy_id, provider) -> dict`; `POST /remedies/{id}/drafts`. Task 8 (Gate) reads `Letter.draft` by `remedy_id`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_remedy_draft.py
import datetime as dt
from decimal import Decimal

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Customer, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.draft import FakeLetterProvider, draft_letter

RUN_ID = "test-draft-run"


def _seed(database_url: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Customer(id="draft-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        session.merge(Complaint(complaint_id="draft-complaint", customer_id="draft-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="draft-complaint", extraction={"claimed_cause": "outage", "issues": ["no internet for 12 hours"], "vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id="draft-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="draft-remedy", cohort_id="draft-cohort", complaint_id="draft-complaint", amount=Decimal("1.75"), policy_rule_id="policy-outage-credit-v1", policy_version=1, rationale="outage credit"))
        session.commit()


def test_draft_letter_includes_exact_amount(database_url_pipeline):
    _seed(database_url_pipeline)
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeLetterProvider()

    result = draft_letter(session_factory, "draft-remedy", provider)

    assert result["drafted"] is True
    with get_session(database_url_pipeline) as session:
        letter = session.query(Letter).filter(Letter.remedy_id == "draft-remedy").one()
        assert "1.75" in letter.draft
        assert letter.gate_result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=... PYTHONPATH=src .venv/bin/python -m pytest tests/test_remedy_draft.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/src/backtrace/remedy/draft.py
"""Gemini letter drafting (§10.2): the LLM fills a template with pre-
computed slots (amount, cause, issues) and may not change the amount or
add commitments — the Gate (Task 8) re-checks both."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Complaint, ComplaintFeatures, Letter, Remedy


class LetterProvider(Protocol):
    model_id: str
    prompt_version: str

    def draft(self, amount: str, claimed_cause: str, issues: list[str]) -> str: ...


@dataclass
class FakeLetterProvider:
    model_id: str = "fake-letter-v1"
    prompt_version: str = "letter-v1"

    def draft(self, amount: str, claimed_cause: str, issues: list[str]) -> str:
        return f"Dear customer, regarding {claimed_cause} ({', '.join(issues)}), we are issuing a credit of ${amount}."


def draft_letter(session_factory: sessionmaker, remedy_id: str, provider: LetterProvider) -> dict:
    with session_factory() as session:
        remedy = session.get(Remedy, remedy_id)
        complaint = session.get(Complaint, remedy.complaint_id)
        features = session.get(ComplaintFeatures, {"run_id": _run_id_for_remedy(session, remedy), "complaint_id": remedy.complaint_id})
        extraction = features.extraction if features else {}

        draft_text = provider.draft(amount=str(remedy.amount), claimed_cause=extraction.get("claimed_cause", "the reported issue"), issues=extraction.get("issues", []))

        session.query(Letter).filter(Letter.remedy_id == remedy_id).delete()  # idempotent re-run
        session.add(Letter(id=f"letter-{remedy_id}", remedy_id=remedy_id, complaint_id=remedy.complaint_id, draft=draft_text, prompt_version=provider.prompt_version, gate_result=None))
        session.commit()
    return {"drafted": True, "remedy_id": remedy_id}


def _run_id_for_remedy(session, remedy: Remedy) -> str:
    from backtrace.db.models import Cohort

    return session.get(Cohort, remedy.cohort_id).run_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Add config, real provider, and endpoint**

```yaml
# configs/pipeline.yaml — add after hypothesis
letter_drafting:
  model_id: gemini-flash-lite-latest
  prompt_version: letter-v1
```

```python
# backend/src/backtrace/llm/providers.py — append
class GeminiLetterProvider:
    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"], http_options={"timeout": REQUEST_TIMEOUT_MS, "retry_options": NO_RETRY})

    def draft(self, amount: str, claimed_cause: str, issues: list[str]) -> str:
        from backtrace.llm.prompts import LETTER_PROMPT_V1

        prompt = LETTER_PROMPT_V1.format(amount=amount, claimed_cause=claimed_cause, issues=", ".join(issues))
        resp = self._client.models.generate_content(model=self.model_id, contents=prompt)
        return resp.text.strip()
```

```python
# backend/src/backtrace/api/remedies.py — new file
import os
from typing import Annotated

from fastapi import APIRouter, Depends

from backtrace.api.auth import CurrentUser, current_user
from backtrace.audit import append_audit
from backtrace.contracts.remedy import LetterDraftOut
from backtrace.db.session import get_session, make_session_factory
from backtrace.remedy.draft import draft_letter

router = APIRouter()


@router.post("/remedies/{remedy_id}/drafts")
def create_letter_draft(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> LetterDraftOut:
    from backtrace.llm.config import PipelineConfig
    from backtrace.llm.providers import GeminiLetterProvider

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    config = PipelineConfig.load()
    provider = GeminiLetterProvider(config.letter_drafting.model_id, config.letter_drafting.prompt_version)
    result = draft_letter(session_factory, remedy_id, provider)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.draft", "remedy", remedy_id, before={}, after=result)
        session.commit()
    return LetterDraftOut(remedy_id=remedy_id, drafted=result["drafted"])
```

```python
# backend/src/backtrace/contracts/remedy.py — append
class LetterDraftOut(BaseModel):
    remedy_id: str
    drafted: bool
```

```python
# backend/src/backtrace/api/main.py — add
from backtrace.api import remedies
...
app.include_router(remedies.router)
```

Add `letter_drafting: ModelPin` to `PipelineConfig` the same way as `hypothesis` (Task 3, Step 4); add `LETTER_PROMPT_V1` to `prompts.py` instructing the model never to state a different amount than the one given and never to promise anything beyond the credit (§10.2).

- [ ] **Step 6: Run full suite + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... DATABASE_URL_EVAL=... AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass

```bash
git add backend/src/backtrace/remedy/draft.py backend/src/backtrace/api/remedies.py backend/src/backtrace/api/main.py backend/src/backtrace/llm/providers.py backend/src/backtrace/llm/prompts.py backend/src/backtrace/contracts/remedy.py configs/pipeline.yaml backend/tests/test_remedy_draft.py
git commit -m "feat(remedy): Gemini letter drafting with fixed amount/issue slots (§10.2, demo step 7)"
```

---

### Task 8: Consistency Gate

**Files:**
- Create: `backend/src/backtrace/gate/__init__.py`, `backend/src/backtrace/gate/rules.py`, `backend/src/backtrace/gate/consistency.py`
- Modify: `backend/src/backtrace/api/remedies.py` (add `POST /remedies/{id}/gate`), `configs/pipeline.yaml` (add `gate:` section)
- Test: `backend/tests/test_gate_rules.py`, `backend/tests/test_gate_consistency.py`

**Interfaces:**
- Consumes: `Letter`, `Remedy` (Task 1/6/7); `ComplaintFeatures.extraction["issues"]` (existing).
- Produces: `check_amount`, `check_forbidden_phrases`, `check_vulnerability`, `check_cohort_consistency` (pure, each `-> GateCheckResult`); `run_gate(session_factory, letter_id, provider) -> dict` — writes `Letter.gate_result`. Task 9 (approval) reads `Letter.gate_result["status"]`.

- [ ] **Step 1: Write the failing test (pure rules)**

```python
# backend/tests/test_gate_rules.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/test_gate_rules.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement pure rules**

```python
# backend/src/backtrace/gate/rules.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2. Expected: PASS

- [ ] **Step 5: Write the failing test (DB wrapper + LLM check)**

```python
# backend/tests/test_gate_consistency.py
import datetime as dt
from decimal import Decimal

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session, make_session_factory
from backtrace.gate.consistency import FakeGateLlmProvider, run_gate

RUN_ID = "test-gate-run"


def _seed(database_url: str, letter_text: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Complaint(complaint_id="gate-complaint", customer_id="gate-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(ComplaintFeatures(run_id=RUN_ID, complaint_id="gate-complaint", extraction={"issues": ["no internet for 12 hours"], "vulnerability_signals": []}, extraction_version="v1", pii_redacted_text="t", needs_review=False))
        session.merge(Cohort(id="gate-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="gate-remedy", cohort_id="gate-cohort", complaint_id="gate-complaint", amount=Decimal("1.75"), policy_rule_id="policy-outage-credit-v1", policy_version=1, rationale="outage credit"))
        session.merge(Letter(id="gate-letter", remedy_id="gate-remedy", complaint_id="gate-complaint", draft=letter_text, prompt_version="letter-v1", gate_result=None))
        session.commit()


def test_gate_passes_when_amount_matches_and_issues_addressed(database_url_pipeline):
    _seed(database_url_pipeline, "Dear customer, we are issuing a credit of $1.75 for no internet for 12 hours.")
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeGateLlmProvider(fake_all_issues_addressed=True)

    result = run_gate(session_factory, "gate-letter", provider)

    assert result["status"] == "pass"
    with get_session(database_url_pipeline) as session:
        letter = session.get(Letter, "gate-letter")
        assert letter.gate_result["status"] == "pass"


def test_gate_fails_fast_on_amount_mismatch_without_calling_llm(database_url_pipeline):
    _seed(database_url_pipeline, "Dear customer, we are issuing a credit of $99.00.")
    session_factory = make_session_factory(database_url_pipeline)
    provider = FakeGateLlmProvider(fake_all_issues_addressed=True, fail_if_called=True)

    result = run_gate(session_factory, "gate-letter", provider)

    assert result["status"] == "fail"
    assert "amount" in result["reason"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=... PYTHONPATH=src .venv/bin/python -m pytest tests/test_gate_consistency.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 7: Implement the DB wrapper**

```python
# backend/src/backtrace/gate/consistency.py
"""Consistency Gate orchestration (§10.3): rules first (free), then the one
LLM check ("every issue addressed"), only if every rule already passed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Cohort, Complaint, ComplaintFeatures, Letter, Remedy
from backtrace.gate.rules import check_amount, check_forbidden_phrases, check_vulnerability

FORBIDDEN_PHRASES = ("guarantee", "lifetime", "unlimited")


class GateLlmProvider(Protocol):
    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool: ...


@dataclass
class FakeGateLlmProvider:
    fake_all_issues_addressed: bool = True
    fail_if_called: bool = False

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool:
        if self.fail_if_called:
            raise AssertionError("LLM check must not run when a rule already failed")
        return self.fake_all_issues_addressed


def run_gate(session_factory: sessionmaker, letter_id: str, provider: GateLlmProvider) -> dict:
    with session_factory() as session:
        letter = session.get(Letter, letter_id)
        remedy = session.get(Remedy, letter.remedy_id)
        cohort = session.get(Cohort, remedy.cohort_id)
        features = session.get(ComplaintFeatures, {"run_id": cohort.run_id, "complaint_id": letter.complaint_id})
        extraction = features.extraction if features else {}

        rule_results = [
            check_amount(letter.draft, remedy.amount),
            check_forbidden_phrases(letter.draft, FORBIDDEN_PHRASES),
            check_vulnerability(extraction.get("vulnerability_signals", [])),
        ]
        failed = next((r for r in rule_results if not r.passed), None)
        if failed is not None:
            gate_result = {"status": "fail", "reason": f"{failed.check}: {failed.reason}"}
        else:
            addressed = provider.all_issues_addressed(letter.draft, extraction.get("issues", []))
            gate_result = {"status": "pass"} if addressed else {"status": "needs_review", "reason": "not every issue addressed"}

        letter.gate_result = gate_result
        session.commit()
    return gate_result
```

- [ ] **Step 8: Run test to verify it passes**

Run: same as Step 6. Expected: PASS

- [ ] **Step 9: Add real LLM provider, config, and endpoint**

```yaml
# configs/pipeline.yaml — add after letter_drafting
gate:
  model_id: gemini-flash-lite-latest
  prompt_version: gate-v1
  forbidden_phrases: [guarantee, lifetime, unlimited]
```

```python
# backend/src/backtrace/gate/consistency.py — add real provider
class GeminiGateLlmProvider:
    def __init__(self, model_id: str, prompt_version: str, api_key: str | None = None) -> None:
        import os

        from google import genai

        self.model_id = model_id
        self.prompt_version = prompt_version
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])

    def all_issues_addressed(self, letter_text: str, issues: list[str]) -> bool:
        from backtrace.llm.prompts import GATE_ISSUES_PROMPT_V1

        prompt = GATE_ISSUES_PROMPT_V1.format(letter_text=letter_text, issues=", ".join(issues))
        resp = self._client.models.generate_content(model=self.model_id, contents=prompt)
        return resp.text.strip().lower().startswith("yes")
```

```python
# backend/src/backtrace/api/remedies.py — append
@router.post("/remedies/{remedy_id}/gate")
def run_remedy_gate(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> dict:
    from backtrace.db.models import Letter
    from backtrace.gate.consistency import GeminiGateLlmProvider, run_gate
    from backtrace.llm.config import PipelineConfig

    database_url = os.environ["DATABASE_URL_PIPELINE"]
    session_factory = make_session_factory(database_url)
    with get_session(database_url) as session:
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one()
        letter_id = letter.id
    config = PipelineConfig.load()
    provider = GeminiGateLlmProvider(config.gate.model_id, config.gate.prompt_version)
    result = run_gate(session_factory, letter_id, provider)
    with get_session(database_url) as session:
        append_audit(session, user.user_id, user.role, "dev", "letter.gate", "letter", letter_id, before={}, after=result)
        session.commit()
    return result
```

Add `gate: GateConfig` (`model_id`, `prompt_version`, `forbidden_phrases: tuple[str, ...]`) to `llm/config.py` alongside `hypothesis`/`letter_drafting`; add `GATE_ISSUES_PROMPT_V1` to `prompts.py` asking a strict yes/no on whether every listed issue is addressed in the letter.

- [ ] **Step 10: Run full suite + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... DATABASE_URL_EVAL=... AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass

```bash
git add backend/src/backtrace/gate/ backend/src/backtrace/api/remedies.py backend/src/backtrace/llm/config.py backend/src/backtrace/llm/prompts.py configs/pipeline.yaml backend/tests/test_gate_rules.py backend/tests/test_gate_consistency.py
git commit -m "feat(gate): Consistency Gate — rules-first, one LLM check (§10.3, demo step 8)"
```

---

### Task 9: Approval with RBAC threshold + audit

**Files:**
- Modify: `backend/src/backtrace/api/remedies.py` (add `POST /remedies/{id}/approve`)
- Modify: `configs/pipeline.yaml` (add `approval_threshold_amount`, `approval_threshold_customers`)
- Test: `backend/tests/test_api_approve.py`

**Interfaces:**
- Consumes: `Approval` (Task 1); `append_audit` (Task 2); `Letter.gate_result` (Task 8) — approval is refused if the gate hasn't passed.
- Produces: `POST /remedies/{id}/approve`. Frontend Task 12 calls this with the current demo user's role.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_approve.py
import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Approval, Cohort, Complaint, Letter, PipelineRun, Remedy, RemedyPolicy
from backtrace.db.session import get_session

RUN_ID = "test-approve-run"


def _seed(database_url: str, amount: Decimal, gate_status: str) -> None:
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=dt.datetime.now(dt.timezone.utc)))
        session.merge(Complaint(complaint_id="approve-complaint", customer_id="approve-cust", received_at=dt.datetime.now(dt.timezone.utc), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id="approve-cohort", run_id=RUN_ID, status="confirmed", kind="linked"))
        session.merge(RemedyPolicy(id="policy-outage-credit-v1", rule_type="outage_credit", config={"price_table": {"fiber_pro": 3.50}}, version=1))
        session.merge(Remedy(id="approve-remedy", cohort_id="approve-cohort", complaint_id="approve-complaint", amount=amount, policy_rule_id="policy-outage-credit-v1", policy_version=1, rationale="r"))
        session.merge(Letter(id="approve-letter", remedy_id="approve-remedy", complaint_id="approve-complaint", draft="d", prompt_version="v1", gate_result={"status": gate_status}))
        session.commit()


def test_team_lead_can_approve_below_threshold(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "pass")
    client = TestClient(app)

    resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
    assert resp.status_code == 200
    assert resp.json()["decision"] == "approved"


def test_team_lead_cannot_approve_above_threshold(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("5000.00"), "pass")
    client = TestClient(app)

    resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
    assert resp.status_code == 403

    allowed = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-compliance"})
    assert allowed.status_code == 200


def test_cannot_approve_when_gate_has_not_passed(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline, Decimal("1.75"), "fail")
    client = TestClient(app)

    resp = client.post("/remedies/approve-remedy/approve", headers={"X-Demo-User": "demo-team-lead"})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_approve.py -v`
Expected: FAIL with 404 (endpoint doesn't exist)

- [ ] **Step 3: Add threshold config**

```yaml
# configs/pipeline.yaml — add near the bottom
approval_threshold_amount: 1000.00  # §12: above this, requires `compliance` role
```

```python
# backend/src/backtrace/llm/config.py — add
approval_threshold_amount: Decimal
# ...in load():
approval_threshold_amount=Decimal(str(raw["approval_threshold_amount"])),
```

- [ ] **Step 4: Implement the endpoint**

```python
# backend/src/backtrace/api/remedies.py — append
import datetime as dt

from fastapi import HTTPException, status as http_status

from backtrace.contracts.remedy import ApprovalOut
from backtrace.db.models import Approval, Letter, Remedy


@router.post("/remedies/{remedy_id}/approve")
def approve_remedy(remedy_id: str, user: Annotated[CurrentUser, Depends(current_user)]) -> ApprovalOut:
    database_url = os.environ["DATABASE_URL_PIPELINE"]
    from backtrace.llm.config import PipelineConfig

    config = PipelineConfig.load()
    with get_session(database_url) as session:
        remedy = session.get(Remedy, remedy_id)
        if remedy is None:
            raise HTTPException(status_code=404, detail="remedy not found")
        letter = session.query(Letter).filter(Letter.remedy_id == remedy_id).one_or_none()
        if letter is None or letter.gate_result is None or letter.gate_result.get("status") != "pass":
            raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="letter has not passed the Consistency Gate")

        if remedy.amount > config.approval_threshold_amount and user.role != "compliance":
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=f"remedies over {config.approval_threshold_amount} require compliance role")
        if user.role not in {"team_lead", "compliance"}:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="requires team_lead or compliance")

        decided_at = dt.datetime.now(dt.timezone.utc)
        approval = Approval(id=f"approval-{remedy_id}", remedy_id=remedy_id, approver_user_id=user.user_id, role=user.role, auth_mode="dev", mfa_used=False, decision="approved", decided_at=decided_at)
        session.merge(approval)
        append_audit(session, user.user_id, user.role, "dev", "remedy.approve", "remedy", remedy_id, before={}, after={"decision": "approved", "amount": str(remedy.amount)})
        session.commit()
        return ApprovalOut(remedy_id=remedy_id, decision="approved", approver_user_id=user.user_id, role=user.role, decided_at=decided_at)
```

```python
# backend/src/backtrace/contracts/remedy.py — append
import datetime as dt


class ApprovalOut(BaseModel):
    remedy_id: str
    decision: str
    approver_user_id: str
    role: str
    decided_at: dt.datetime
```

- [ ] **Step 5: Run test to verify it passes**

Run: same as Step 2. Expected: PASS (all three tests)

- [ ] **Step 6: Run full suite + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... DATABASE_URL_EVAL=... AUTH_MODE=dev PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass

```bash
git add backend/src/backtrace/api/remedies.py backend/src/backtrace/contracts/remedy.py backend/src/backtrace/llm/config.py configs/pipeline.yaml backend/tests/test_api_approve.py
git commit -m "feat(api): remedy approval with RBAC threshold + gate-pass requirement (§12, demo step 9)"
```

---

### Task 10: Frontend — cohort list + detail scaffold

**Files:**
- Modify: `apps/web/src/lib/api.ts` (add fetchers)
- Create: `apps/web/src/app/cohorts/page.tsx`, `apps/web/src/app/cohorts/[id]/page.tsx`
- Create: `apps/web/src/components/ui/dialog.tsx`, `apps/web/src/components/ui/badge.tsx` (via shadcn CLI)

**Interfaces:**
- Consumes: `GET /cohorts`, `GET /cohorts/{id}` (Task 4); existing `apps/web/src/lib/api.ts` fetch-wrapper pattern (read it first — `grep -n "export async function" apps/web/src/lib/api.ts` — to match its existing error handling / base-URL convention).
- Produces: cohort list page (demo steps 2–3) and a detail page shell that Task 11 (evidence timeline) and Task 12 (remedy/letter/gate/approve panel) render into.

- [ ] **Step 1: Install shadcn components**

Run: `cd apps/web && pnpm dlx shadcn@latest add dialog badge select`
Expected: `src/components/ui/dialog.tsx`, `badge.tsx`, `select.tsx` created

- [ ] **Step 2: Add typed fetchers**

Read `apps/web/src/lib/api.ts` first and match its existing function signature style exactly (likely `fetchJson<T>(path, init?)` or similar — do not invent a second pattern). Example shape assuming a `fetchJson` helper exists:

```typescript
// apps/web/src/lib/api.ts — append
export type CohortOut = {
  id: string;
  run_id: string;
  status: string;
  kind: string;
  hypothesis: string | null;
  confidence: number | null;
  member_count: number;
};

export type CohortEvidenceOut = {
  cohort_id: string;
  score_components: Record<string, number>;
  hypothesis: string | null;
  hypothesis_citations: { complaint_ids: string[]; event_ids: string[]; anomaly_ids: string[] } | null;
  linked_event_ids: string[];
  linked_anomaly_ids: string[];
  sample_complaint_ids: string[];
};

export async function listCohorts(runId: string): Promise<{ cohorts: CohortOut[] }> {
  return fetchJson(`/cohorts?run_id=${encodeURIComponent(runId)}`);
}

export async function getCohort(id: string): Promise<CohortOut> {
  return fetchJson(`/cohorts/${id}`);
}

export async function getCohortEvidence(id: string): Promise<CohortEvidenceOut> {
  return fetchJson(`/cohorts/${id}/evidence`);
}
```

- [ ] **Step 3: Cohort list page**

```tsx
// apps/web/src/app/cohorts/page.tsx
import Link from "next/link";
import { listCohorts } from "@/lib/api";

export default async function CohortsPage() {
  // Day 2's page.tsx fetches /runs/latest first to get a run_id — reuse that
  // call here (read apps/web/src/app/page.tsx for the existing pattern)
  // instead of hardcoding a run_id.
  const { cohorts } = await listCohorts(await latestRunId());

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold mb-4">Cohorts</h1>
      <ul className="space-y-2">
        {cohorts.map((cohort) => (
          <li key={cohort.id}>
            <Link href={`/cohorts/${cohort.id}`} className="block rounded border p-4 hover:bg-neutral-50">
              <div className="flex justify-between">
                <span className="font-medium">{cohort.id}</span>
                <span className="text-sm text-neutral-500">{cohort.status} · {cohort.member_count} members</span>
              </div>
              {cohort.hypothesis && <p className="text-sm text-neutral-700 mt-1">{cohort.hypothesis}</p>}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

(`latestRunId()` — write as a one-line helper calling the existing `/runs/latest` fetcher already used by `apps/web/src/app/page.tsx`; read that file first to match it exactly rather than re-deriving the run_id fetch independently.)

- [ ] **Step 4: Cohort detail page shell**

```tsx
// apps/web/src/app/cohorts/[id]/page.tsx
import { getCohort, getCohortEvidence } from "@/lib/api";

export default async function CohortDetailPage({ params }: { params: { id: string } }) {
  const [cohort, evidence] = await Promise.all([getCohort(params.id), getCohortEvidence(params.id)]);

  return (
    <main className="p-8 space-y-6">
      <h1 className="text-2xl font-semibold">{cohort.id}</h1>
      <p className="text-neutral-600">{cohort.status} · {cohort.member_count} members</p>
      {cohort.hypothesis && (
        <div className="rounded border p-4 bg-neutral-50">
          <p className="font-medium">Hypothesis</p>
          <p>{cohort.hypothesis}</p>
        </div>
      )}
      {/* Task 11 renders <EvidenceTimeline evidence={evidence} /> here */}
      {/* Task 12 renders the remedy/letter/gate/approve panel here */}
    </main>
  );
}
```

- [ ] **Step 5: Manual check**

Run: `cd apps/web && pnpm dev`, open `http://localhost:3000/cohorts` in a browser
Expected: cohort list renders for `dev-run-3` (or whichever run has cohorts in the local DB at the time); clicking a cohort opens its detail page with hypothesis shown if present

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/app/cohorts apps/web/src/components/ui/dialog.tsx apps/web/src/components/ui/badge.tsx apps/web/src/components/ui/select.tsx apps/web/package.json apps/web/pnpm-lock.yaml
git commit -m "feat(web): cohort list + detail page scaffold (demo steps 2-3)"
```

---

### Task 11: Frontend — evidence view (ECharts timeline)

**Files:**
- Modify: `apps/web/package.json` (add `echarts`, `echarts-for-react`)
- Create: `apps/web/src/components/evidence-timeline.tsx`
- Modify: `apps/web/src/app/cohorts/[id]/page.tsx` (render the component)

**Interfaces:**
- Consumes: `CohortEvidenceOut` (Task 10's type); needs complaint-burst and telemetry-anomaly time-series data not yet exposed by any endpoint — **this task adds `GET /cohorts/{id}/timeline`** returning bucketed complaint counts + anomaly windows, since `CohortEvidenceOut` only has ids/scores, not a time axis.
- Produces: `<EvidenceTimeline />` component — demo step 4's core visual.

- [ ] **Step 1: Install dependency**

Run: `cd apps/web && pnpm add echarts echarts-for-react`

- [ ] **Step 2: Write the failing backend test for the new timeline endpoint**

```python
# backend/tests/test_api_cohort_timeline.py
import datetime as dt

from fastapi.testclient import TestClient

from backtrace.api.main import app
from backtrace.db.models import Cohort, CohortEventLink, CohortMember, Complaint, Customer, DetectedAnomaly, PipelineRun
from backtrace.db.session import get_session

RUN_ID = "test-timeline-run"
COHORT_ID = "test-timeline-cohort"


def _seed(database_url: str) -> None:
    base = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    with get_session(database_url) as session:
        session.merge(PipelineRun(run_id=RUN_ID, dataset_profile="dev", dataset_seed=1, config={}, started_at=base))
        session.merge(Customer(id="tl-cust", region="north", plan="fiber_pro", segment="residential", node_id="n1"))
        for i in range(3):
            session.merge(Complaint(complaint_id=f"tl-complaint-{i}", customer_id="tl-cust", received_at=base + dt.timedelta(minutes=10 * i), channel="web", text="t", product="fiber_pro", region="north", node_id="n1"))
        session.merge(Cohort(id=COHORT_ID, run_id=RUN_ID, status="confirmed", kind="linked"))
        for i in range(3):
            session.merge(CohortMember(run_id=RUN_ID, complaint_id=f"tl-complaint-{i}", cohort_id=COHORT_ID, membership_score=1.0, assigned_by="batch", needs_review=False))
        session.merge(DetectedAnomaly(id="tl-anomaly", run_id=RUN_ID, node_id="n1", metric="packet_loss_pct", start_at=base, end_at=base + dt.timedelta(hours=1), peak_score=9.0, method="rolling_z_v1"))
        session.merge(CohortEventLink(cohort_id=COHORT_ID, run_id=RUN_ID, anomaly_id="tl-anomaly", overlap_score=5.0, evidence={}))
        session.commit()


def test_cohort_timeline_returns_complaint_buckets_and_anomaly_windows(database_url_pipeline, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PIPELINE", database_url_pipeline)
    monkeypatch.setenv("AUTH_MODE", "dev")
    _seed(database_url_pipeline)
    client = TestClient(app)

    resp = client.get(f"/cohorts/{COHORT_ID}/timeline", headers={"X-Demo-User": "demo-agent"})
    assert resp.status_code == 200
    body = resp.json()
    assert sum(b["count"] for b in body["complaint_buckets"]) == 3
    assert body["anomaly_windows"][0]["metric"] == "packet_loss_pct"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && DATABASE_URL_PIPELINE=... PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_cohort_timeline.py -v`
Expected: FAIL with 404

- [ ] **Step 4: Implement the endpoint**

```python
# backend/src/backtrace/contracts/evidence.py — append
class ComplaintBucketOut(BaseModel):
    bucket_start: str
    count: int


class AnomalyWindowOut(BaseModel):
    anomaly_id: str
    metric: str
    start_at: str
    end_at: str
    peak_score: float


class CohortTimelineOut(BaseModel):
    cohort_id: str
    complaint_buckets: list[ComplaintBucketOut]
    anomaly_windows: list[AnomalyWindowOut]
```

```python
# backend/src/backtrace/api/cohorts.py — append
from backtrace.contracts.evidence import AnomalyWindowOut, CohortTimelineOut, ComplaintBucketOut
from backtrace.db.models import CohortEventLink, Complaint, DetectedAnomaly

TIMELINE_BUCKET_MINUTES = 15


@router.get("/cohorts/{cohort_id}/timeline")
def get_cohort_timeline(cohort_id: str, _user: Annotated[CurrentUser, Depends(current_user)]) -> CohortTimelineOut:
    with get_session(os.environ["DATABASE_URL_PIPELINE"]) as session:
        cohort = session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status_code=404, detail="cohort not found")

        complaint_ids = [row[0] for row in session.execute(select(CohortMember.complaint_id).where(CohortMember.cohort_id == cohort_id))]
        received_ats = [
            row[0] for row in session.execute(select(Complaint.received_at).where(Complaint.complaint_id.in_(complaint_ids)))
        ]
        buckets: dict = {}
        for received_at in received_ats:
            bucket_start = received_at.replace(minute=(received_at.minute // TIMELINE_BUCKET_MINUTES) * TIMELINE_BUCKET_MINUTES, second=0, microsecond=0)
            buckets[bucket_start] = buckets.get(bucket_start, 0) + 1
        complaint_buckets = [ComplaintBucketOut(bucket_start=k.isoformat(), count=v) for k, v in sorted(buckets.items())]

        links = session.execute(select(CohortEventLink).where(CohortEventLink.cohort_id == cohort_id, CohortEventLink.anomaly_id.isnot(None))).scalars().all()
        anomaly_windows = []
        for link in links:
            anomaly = session.get(DetectedAnomaly, link.anomaly_id)
            anomaly_windows.append(AnomalyWindowOut(anomaly_id=anomaly.id, metric=anomaly.metric, start_at=anomaly.start_at.isoformat(), end_at=anomaly.end_at.isoformat(), peak_score=anomaly.peak_score))

        return CohortTimelineOut(cohort_id=cohort_id, complaint_buckets=complaint_buckets, anomaly_windows=anomaly_windows)
```

- [ ] **Step 5: Run test to verify it passes**

Run: same as Step 3. Expected: PASS

- [ ] **Step 6: Frontend component**

```tsx
// apps/web/src/components/evidence-timeline.tsx
"use client";

import ReactECharts from "echarts-for-react";

type ComplaintBucket = { bucket_start: string; count: number };
type AnomalyWindow = { anomaly_id: string; metric: string; start_at: string; end_at: string; peak_score: number };

export function EvidenceTimeline({ complaintBuckets, anomalyWindows }: { complaintBuckets: ComplaintBucket[]; anomalyWindows: AnomalyWindow[] }) {
  const option = {
    xAxis: { type: "time" },
    yAxis: { type: "value", name: "complaints" },
    series: [
      {
        name: "Complaint bursts",
        type: "bar",
        data: complaintBuckets.map((b) => [b.bucket_start, b.count]),
        markArea: {
          itemStyle: { color: "rgba(255, 0, 0, 0.1)" },
          data: anomalyWindows.map((w) => [{ xAxis: w.start_at, name: w.metric }, { xAxis: w.end_at }]),
        },
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 320 }} />;
}
```

- [ ] **Step 7: Wire into the detail page**

```tsx
// apps/web/src/app/cohorts/[id]/page.tsx — add import and render
import { EvidenceTimeline } from "@/components/evidence-timeline";
// ...
<EvidenceTimeline complaintBuckets={timeline.complaint_buckets} anomalyWindows={timeline.anomaly_windows} />
```

(Add `getCohortTimeline` to `apps/web/src/lib/api.ts` following the same pattern as Task 10 Step 2, and fetch it alongside `cohort`/`evidence` in the page's `Promise.all`.)

- [ ] **Step 8: Manual check**

Run: `cd apps/web && pnpm dev`, open a cohort detail page
Expected: a bar chart of complaint counts over time with anomaly windows shaded via `markArea`

- [ ] **Step 9: Run backend tests + commit**

Run: `cd backend && DATABASE_URL_PIPELINE=... PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: all pass

```bash
git add backend/src/backtrace/contracts/evidence.py backend/src/backtrace/api/cohorts.py backend/tests/test_api_cohort_timeline.py apps/web/src/components/evidence-timeline.tsx apps/web/src/app/cohorts/[id]/page.tsx apps/web/src/lib/api.ts apps/web/package.json apps/web/pnpm-lock.yaml
git commit -m "feat: evidence-view timeline — complaint bursts x telemetry anomalies (§8.2 step 4, demo step 4)"
```

---

### Task 12: Frontend — review, remedy, letter, gate, approve panel + demo-user switcher

**Files:**
- Create: `apps/web/src/components/demo-user-switcher.tsx`, `apps/web/src/components/cohort-action-panel.tsx`
- Modify: `apps/web/src/lib/api.ts` (add remaining fetchers + `X-Demo-User` cookie plumbing), `apps/web/src/app/cohorts/[id]/page.tsx`, `apps/web/src/app/layout.tsx` (mount the switcher globally)
- Modify: `backend/src/backtrace/contracts/remedy.py` (add `remedy_ids: list[str]` to `RemedyComputeOut`, Task 6), `backend/src/backtrace/remedy/engine.py` (return the created ids)

**Interfaces:**
- Consumes: every write endpoint from Tasks 5/6/7/8/9 (`confirm`, `/remedy`, `/drafts`, `/gate`, `/approve`); existing dev-auth cookie mechanism (`demo_user` cookie, read by `api/auth.py::demo_user_cookie`).
- Produces: the UI half of demo steps 5–9 — this is the last task; after it, "Demo steps 1–9 work on `dev` through the UI" (Day 4's done-criterion) is checkable by hand.

- [ ] **Step 1: Close Task 6's remedy-id gap first**

`compute_cohort_remedies` (Task 6) returns counts only; the UI needs the created `Remedy.id`s to chain into draft/gate/approve. Modify `RemedyComputeOut` to add `remedy_ids: list[str]`, and `compute_cohort_remedies` to collect `f"{cohort_id}-{complaint_id}"` for each computed remedy into the returned dict's `"remedy_ids"` key. Update `test_remedy_engine.py`'s assertion to also check `result["remedy_ids"] == ["eng-complaint-1"]`-derived id. Run the backend suite to confirm no regression before continuing.

- [ ] **Step 2: Demo-user switcher**

```tsx
// apps/web/src/components/demo-user-switcher.tsx
"use client";

import { useState } from "react";

const DEMO_USERS = ["demo-agent", "demo-team-lead", "demo-compliance"] as const;

export function DemoUserSwitcher() {
  const [current, setCurrent] = useState<string>(DEMO_USERS[0]);

  function select(user: string) {
    document.cookie = `demo_user=${user}; path=/`;
    setCurrent(user);
    window.location.reload(); // simplest correctness: re-fetch every server component with the new identity
  }

  return (
    <div className="flex gap-2 items-center p-2 border-b bg-neutral-50">
      <span className="text-sm text-neutral-500">Acting as:</span>
      {DEMO_USERS.map((user) => (
        <button key={user} onClick={() => select(user)} className={`text-sm px-2 py-1 rounded ${user === current ? "bg-black text-white" : "bg-white border"}`}>
          {user}
        </button>
      ))}
    </div>
  );
}
```

(Mount `<DemoUserSwitcher />` once in `apps/web/src/app/layout.tsx`, above `{children}` — read that file first to add it without disturbing the existing layout structure.)

- [ ] **Step 3: Action panel fetchers**

```typescript
// apps/web/src/lib/api.ts — append
export async function confirmCohort(id: string) {
  return fetchJson(`/cohorts/${id}/confirm`, { method: "POST" });
}

export async function runCohortRemedy(id: string, policyRuleId: string): Promise<{ remedy_ids: string[] }> {
  return fetchJson(`/cohorts/${id}/remedy?policy_rule_id=${encodeURIComponent(policyRuleId)}`, { method: "POST" });
}

export async function draftLetter(remedyId: string) {
  return fetchJson(`/remedies/${remedyId}/drafts`, { method: "POST" });
}

export async function runGate(remedyId: string) {
  return fetchJson(`/remedies/${remedyId}/gate`, { method: "POST" });
}

export async function approveRemedy(remedyId: string) {
  return fetchJson(`/remedies/${remedyId}/approve`, { method: "POST" });
}
```

(These assume the existing `fetchJson` helper already forwards cookies to the API — confirm with `grep -n "credentials" apps/web/src/lib/api.ts`; if it doesn't set `credentials: "include"`, add it, since the demo-user identity travels via the `demo_user` cookie.)

- [ ] **Step 4: Action panel component**

```tsx
// apps/web/src/components/cohort-action-panel.tsx
"use client";

import { useState } from "react";
import { approveRemedy, confirmCohort, draftLetter, runCohortRemedy, runGate } from "@/lib/api";

const DEFAULT_OUTAGE_POLICY = "policy-outage-credit-v1";

export function CohortActionPanel({ cohortId }: { cohortId: string }) {
  const [log, setLog] = useState<string[]>([]);
  const [remedyIds, setRemedyIds] = useState<string[]>([]);

  async function run<T>(label: string, action: () => Promise<T>): Promise<T> {
    try {
      const result = await action();
      setLog((prev) => [...prev, `${label}: ${JSON.stringify(result)}`]);
      return result;
    } catch (err) {
      setLog((prev) => [...prev, `${label} FAILED: ${String(err)}`]);
      throw err;
    }
  }

  const firstRemedyId = remedyIds[0] ?? null;

  return (
    <div className="space-y-3 rounded border p-4">
      <div className="flex gap-2">
        <button className="px-3 py-1 rounded bg-black text-white" onClick={() => run("confirm", () => confirmCohort(cohortId))}>
          Confirm cohort
        </button>
        <button
          className="px-3 py-1 rounded bg-black text-white"
          onClick={async () => {
            const result = await run("remedy", () => runCohortRemedy(cohortId, DEFAULT_OUTAGE_POLICY));
            setRemedyIds(result.remedy_ids);
          }}
        >
          Compute remedy
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("draft", () => draftLetter(firstRemedyId))}>
          Draft letter
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("gate", () => runGate(firstRemedyId))}>
          Run gate
        </button>
        <button className="px-3 py-1 rounded bg-black text-white" disabled={!firstRemedyId} onClick={() => firstRemedyId && run("approve", () => approveRemedy(firstRemedyId))}>
          Approve
        </button>
      </div>
      <pre className="text-xs bg-neutral-50 p-2 rounded max-h-40 overflow-auto">{log.join("\n")}</pre>
    </div>
  );
}
```

(This demo panel drives only the first remedy in the cohort end to end, one button chain at a time — looping over every member's remedy in the UI is a further iteration, not needed for the done-criterion's single walkthrough.)

- [ ] **Step 5: Wire into the detail page**

```tsx
// apps/web/src/app/cohorts/[id]/page.tsx — add import and render
import { CohortActionPanel } from "@/components/cohort-action-panel";
// ...
<CohortActionPanel cohortId={cohort.id} />
```

- [ ] **Step 6: Manual end-to-end check (demo steps 5-9)**

Run: `cd apps/web && pnpm dev` (and `cd backend && ... uvicorn backtrace.api.main:app` per existing Day 1-2 run instructions)
Steps: switch to `demo-team-lead` → open a cohort → Confirm cohort → Compute remedy → Draft letter → Run gate → Approve
Expected: each button's log line shows a success response; a 1000+ remedy amount with the agent/team_lead user shows the 403 from Task 9; approving before the gate passes shows the 409 from Task 9

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/demo-user-switcher.tsx apps/web/src/components/cohort-action-panel.tsx apps/web/src/lib/api.ts apps/web/src/app/cohorts/[id]/page.tsx apps/web/src/app/layout.tsx backend/src/backtrace/contracts/remedy.py backend/src/backtrace/remedy/engine.py backend/tests/test_remedy_engine.py
git commit -m "feat(web): review/remedy/letter/gate/approve panel + demo-user switcher (demo steps 5-9)"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** §8.2 step 8 (hypothesis) → Task 3. §8.2 step 10 (confirm/split/merge) → Task 5 (split/merge are status-only; re-linking is explicitly deferred, see Task 5's note). §10.1 (remedy engine) → Task 6. §10.2 (letter drafting) → Task 7. §10.3 (Gate) → Task 8. §12 (auth/RBAC/threshold/audit) → Tasks 2, 5, 9. Demo steps 1–3 → Task 4 + 10 (step 1–2's deck.gl scatter/animation already exist from Day 1–2 and are not touched here). Demo step 4 → Task 11. Demo steps 5–9 → Tasks 5–9 (API) + Task 12 (UI).
- **Fixed during self-review:** Task 12's original draft used a hardcoded placeholder `remedyId` string, which would not have worked — resolved by adding `remedy_ids` to `RemedyComputeOut` (Task 12, Step 1) instead of shipping the placeholder.
- **One deliberately flagged gap, called out inline rather than silently built:** split/merge (Task 5) don't re-run linking for affected cohorts, per §8.2 step 10 — needs a separate design decision on cohort re-linking scope, and isn't required for the demo-step-5 walkthrough (which only exercises `confirm`).
- **Out of scope by spec, not by oversight:** hybrid search/retrieval (§9, explicitly Day 6), online path (§8.4, Day 5), Auth0 (§12, Day 6), step-up MFA (§12 stretch).
