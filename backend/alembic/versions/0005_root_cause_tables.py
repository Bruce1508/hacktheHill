"""Day 3 root-cause tables (§8.2 steps 4-6, §8.3): anomalies, bursts,
symptom clusters, cohorts, and cohort-to-evidence links.

All new tables live in schema `app` with an indexed `run_id`. Grants to
`bt_pipeline` need no new statement here — migration 0001's `ALTER DEFAULT
PRIVILEGES IN SCHEMA app` already covers tables created later by the same
owner role.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "detected_anomalies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("node_id", sa.String, sa.ForeignKey("app.network_nodes.id"), nullable=True),
        sa.Column("link_id", sa.String, sa.ForeignKey("app.network_links.id"), nullable=True),
        sa.Column("metric", sa.String, nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("peak_score", sa.Float, nullable=False),
        sa.Column("method", sa.String, nullable=False),  # "rolling_z_v1"
        schema="app",
    )
    op.create_index("ix_app_detected_anomalies_run_id", "detected_anomalies", ["run_id"], schema="app")

    op.create_table(
        "complaint_bursts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complaint_count", sa.Integer, nullable=False),
        sa.Column("peak_score", sa.Float, nullable=False),
        schema="app",
    )
    op.create_index("ix_app_complaint_bursts_run_id", "complaint_bursts", ["run_id"], schema="app")

    op.create_table(
        "symptom_clusters",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("label", sa.Integer, nullable=False),  # HDBSCAN label, >= 0
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("method", sa.String, nullable=False),  # "text" | "text+structured"
        schema="app",
    )
    op.create_index("ix_app_symptom_clusters_run_id", "symptom_clusters", ["run_id"], schema="app")

    op.create_table(
        "symptom_cluster_members",
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), primary_key=True),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("cluster_id", sa.String, sa.ForeignKey("app.symptom_clusters.id"), nullable=True),  # null = noise
        schema="app",
    )

    op.create_table(
        "cohorts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="proposed"),
        sa.Column("kind", sa.String, nullable=False),  # "linked" | "no_linked_evidence"
        sa.Column("hypothesis", sa.String, nullable=True),
        sa.Column("hypothesis_citations", sa.JSON, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        schema="app",
    )
    op.create_index("ix_app_cohorts_run_id", "cohorts", ["run_id"], schema="app")

    op.create_table(
        "cohort_members",
        # PK is (run_id, complaint_id), not (cohort_id, complaint_id): §8.3
        # assigns each complaint to exactly one candidate/cohort, so a
        # complaint can have at most one membership row per run — the same
        # per-complaint-per-run uniqueness ComplaintFeatures/
        # ComplaintEmbedding/ComplaintLayout already enforce.
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), primary_key=True),
        sa.Column("complaint_id", sa.String, sa.ForeignKey("app.complaints.complaint_id"), primary_key=True),
        sa.Column("cohort_id", sa.String, sa.ForeignKey("app.cohorts.id"), nullable=False),
        sa.Column("membership_score", sa.Float, nullable=False),
        sa.Column("assigned_by", sa.String, nullable=False),  # "batch"
        sa.Column("needs_review", sa.Boolean, nullable=False),
        schema="app",
    )
    op.create_index("ix_app_cohort_members_cohort_id", "cohort_members", ["cohort_id"], schema="app")

    op.create_table(
        "cohort_event_links",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("cohort_id", sa.String, sa.ForeignKey("app.cohorts.id"), nullable=False),
        sa.Column("run_id", sa.String, sa.ForeignKey("app.pipeline_runs.run_id"), nullable=False),
        sa.Column("event_id", sa.String, sa.ForeignKey("app.events.id"), nullable=True),
        sa.Column("anomaly_id", sa.String, sa.ForeignKey("app.detected_anomalies.id"), nullable=True),
        sa.Column("overlap_score", sa.Float, nullable=False),
        sa.Column("time_offset_minutes", sa.Float, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.CheckConstraint("event_id IS NOT NULL OR anomaly_id IS NOT NULL", name="ck_app_cohort_event_links_has_evidence"),
        schema="app",
    )
    op.create_index("ix_app_cohort_event_links_run_id", "cohort_event_links", ["run_id"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_cohort_event_links_run_id", table_name="cohort_event_links", schema="app")
    op.drop_table("cohort_event_links", schema="app")
    op.drop_index("ix_app_cohort_members_cohort_id", table_name="cohort_members", schema="app")
    op.drop_table("cohort_members", schema="app")
    op.drop_index("ix_app_cohorts_run_id", table_name="cohorts", schema="app")
    op.drop_table("cohorts", schema="app")
    op.drop_table("symptom_cluster_members", schema="app")
    op.drop_index("ix_app_symptom_clusters_run_id", table_name="symptom_clusters", schema="app")
    op.drop_table("symptom_clusters", schema="app")
    op.drop_index("ix_app_complaint_bursts_run_id", table_name="complaint_bursts", schema="app")
    op.drop_table("complaint_bursts", schema="app")
    op.drop_index("ix_app_detected_anomalies_run_id", table_name="detected_anomalies", schema="app")
    op.drop_table("detected_anomalies", schema="app")
