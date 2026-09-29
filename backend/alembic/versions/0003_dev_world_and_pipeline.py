"""dev-world storage (topology, telemetry, eval gold tables) and pipeline
run/stage tables (embeddings, jobs, cache) for Day 2.

`app.complaint_embeddings.embedding` is pinned to vector(768) — a placeholder
until Phase 0's Gemini quota/model check (Day 2 plan) confirms the real
embedding model and output_dimensionality. Changing it is a follow-up
`ALTER COLUMN ... TYPE vector(n)` migration, not a rewrite of this one.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # --- app: topology + customer/complaint fields the dev generator fills in ---
    op.add_column("customers", sa.Column("tenure_months", sa.Integer, nullable=True), schema="app")

    op.create_table(
        "network_nodes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        schema="app",
    )
    op.create_table(
        "network_links",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("from_node_id", sa.String, sa.ForeignKey("app.network_nodes.id"), nullable=False),
        sa.Column("to_node_id", sa.String, sa.ForeignKey("app.network_nodes.id"), nullable=False),
        sa.Column("redundant", sa.Boolean, nullable=False, server_default=sa.false()),
        schema="app",
    )

    op.add_column("complaints", sa.Column("is_repeat", sa.Boolean, nullable=False, server_default=sa.false()), schema="app")
    op.add_column("complaints", sa.Column("prior_complaint_ids", sa.JSON, nullable=False, server_default="[]"), schema="app")
    op.add_column("complaints", sa.Column("escalation_status", sa.String, nullable=False, server_default="open"), schema="app")
    op.add_column("complaints", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.add_column("complaints", sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True), schema="app")

    # --- app.telemetry: hypertable, samples for both nodes and links ---
    op.create_table(
        "telemetry",
        sa.Column("node_id", sa.String, sa.ForeignKey("app.network_nodes.id"), nullable=True),
        sa.Column("link_id", sa.String, sa.ForeignKey("app.network_links.id"), nullable=True),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("optical_power_dbm", sa.Float, nullable=False),
        sa.Column("errored_seconds", sa.Integer, nullable=False),
        sa.Column("packet_loss_pct", sa.Float, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("alarm", sa.Boolean, nullable=False),
        # NULLS NOT DISTINCT: node rows (link_id NULL) and link rows (node_id NULL)
        # each still get one row per (node|link, sampled_at); reseeding upserts, not duplicates.
        sa.UniqueConstraint("node_id", "link_id", "sampled_at", name="uq_app_telemetry_key", postgresql_nulls_not_distinct=True),
        schema="app",
    )
    op.execute("SELECT create_hypertable('app.telemetry', 'sampled_at');")
    op.create_index("ix_app_telemetry_node_sampled_at", "telemetry", ["node_id", "sampled_at"], schema="app")
    op.create_index("ix_app_telemetry_link_sampled_at", "telemetry", ["link_id", "sampled_at"], schema="app")

    # --- app: pipeline run/stage tables (Phase 3-5 write to these; created now
    # so role grants and idempotency constraints land in one place) ---
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("dataset_profile", sa.String, nullable=False),
        sa.Column("dataset_seed", sa.Integer, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage_timings", sa.JSON, nullable=True),
        schema="app",
    )

    op.create_table(
        "complaint_features",
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), primary_key=True),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("extraction", sa.JSON, nullable=False),
        sa.Column("extraction_version", sa.String, nullable=False),
        sa.Column("pii_redacted_text", sa.String, nullable=False),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        schema="app",
    )

    op.create_table(
        "complaint_embeddings",
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), primary_key=True),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("model_version", sa.String, nullable=False),
        schema="app",
    )
    # vector(n) has no parameterized-DDL form, so the dimension is a literal here.
    op.execute("ALTER TABLE app.complaint_embeddings ADD COLUMN embedding vector(768) NOT NULL;")

    op.create_table(
        "complaint_layout",
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), primary_key=True),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("x", sa.Float, nullable=False),
        sa.Column("y", sa.Float, nullable=False),
        sa.Column("layout_version", sa.String, nullable=False),
        schema="app",
    )

    op.create_table(
        "llm_cache",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("response", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="app",
    )

    op.create_table(
        "llm_calls",
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("prompt_version", sa.String, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("cost_estimate", sa.Numeric(10, 4), nullable=False),
        sa.Column("cache_hit", sa.Boolean, nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.execute("SELECT create_hypertable('app.llm_calls', 'called_at');")

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("type", sa.String, nullable=False),  # pipeline.run | pipeline.stage | letters.draft
        sa.Column("stage", sa.String, nullable=True),  # set for pipeline.stage, e.g. "extraction"
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # One row per (run, type, stage): an enqueue that races with a rerun
        # upserts instead of stacking a second queued job for the same work.
        sa.UniqueConstraint("run_id", "type", "stage", name="uq_app_jobs_run_type_stage", postgresql_nulls_not_distinct=True),
        schema="app",
    )

    # --- eval: answer key, bt_eval-only ---
    op.create_table(
        "gold_events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("affected_customer_ids", sa.JSON, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("complaint_probability", sa.Float, nullable=False),
        schema="eval",
    )
    op.create_table(
        "gold_complaint_labels",
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("root_cause_id", sa.String, nullable=True),
        sa.Column("secondary_cause_id", sa.String, nullable=True),
        sa.Column("true_cause", sa.String, nullable=False),
        sa.Column("customer_claimed_cause", sa.String, nullable=True),
        sa.Column("misattributed", sa.Boolean, nullable=False),
        sa.Column("one_off", sa.Boolean, nullable=False),
        sa.Column("multi_issue", sa.Boolean, nullable=False),
        sa.Column("financial_impact", sa.Numeric(10, 2), nullable=False),
        sa.Column("customer_impact_severity", sa.String, nullable=False),
        sa.Column("vulnerability_flag", sa.Boolean, nullable=False),
        sa.Column("vulnerability_mentioned", sa.Boolean, nullable=False),
        sa.Column("gold_remedy", sa.String, nullable=False),
        sa.Column("injected_defect", sa.String, nullable=True),
        schema="eval",
    )


def downgrade() -> None:
    op.drop_table("gold_complaint_labels", schema="eval")
    op.drop_table("gold_events", schema="eval")
    op.drop_table("jobs", schema="app")
    op.drop_table("llm_calls", schema="app")
    op.drop_table("llm_cache", schema="app")
    op.drop_table("complaint_layout", schema="app")
    op.drop_table("complaint_embeddings", schema="app")
    op.drop_table("complaint_features", schema="app")
    op.drop_table("pipeline_runs", schema="app")
    op.drop_index("ix_app_telemetry_link_sampled_at", table_name="telemetry", schema="app")
    op.drop_index("ix_app_telemetry_node_sampled_at", table_name="telemetry", schema="app")
    op.drop_table("telemetry", schema="app")
    op.drop_column("complaints", "sla_deadline", schema="app")
    op.drop_column("complaints", "escalated_at", schema="app")
    op.drop_column("complaints", "escalation_status", schema="app")
    op.drop_column("complaints", "prior_complaint_ids", schema="app")
    op.drop_column("complaints", "is_repeat", schema="app")
    op.drop_table("network_links", schema="app")
    op.drop_table("network_nodes", schema="app")
    op.drop_column("customers", "tenure_months", schema="app")
