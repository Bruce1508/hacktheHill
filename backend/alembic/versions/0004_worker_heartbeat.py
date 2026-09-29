"""single-row worker heartbeat, so /health can report a dead worker (§11)
without depending on Gemini availability.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Boolean, primary_key=True, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id", name="ck_app_worker_heartbeat_singleton"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat", schema="app")
