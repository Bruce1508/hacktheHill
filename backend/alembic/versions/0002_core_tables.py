"""core tables: customers, events, complaints

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("plan", sa.String, nullable=False),
        sa.Column("segment", sa.String, nullable=False),
        sa.Column("node_id", sa.String, nullable=False),
        schema="app",
    )

    op.create_table(
        "events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.JSON, nullable=False),
        sa.Column("search_text", sa.String, nullable=False),
        schema="app",
    )

    op.create_table(
        "complaints",
        sa.Column("complaint_id", sa.String, primary_key=True),
        sa.Column("customer_id", sa.String, sa.ForeignKey("app.customers.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("text", sa.String, nullable=False),
        sa.Column("product", sa.String, nullable=False),
        sa.Column("region", sa.String, nullable=False),
        sa.Column("node_id", sa.String, nullable=False),
        schema="app",
    )
    op.create_index("ix_app_complaints_received_at", "complaints", ["received_at"], schema="app")


def downgrade() -> None:
    op.drop_table("complaints", schema="app")
    op.drop_table("events", schema="app")
    op.drop_table("customers", schema="app")
