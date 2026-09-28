"""schemas and roles

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""
import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _create_role_if_missing(role: str, password: str) -> None:
    op.execute(f"""
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
        CREATE ROLE {role} LOGIN PASSWORD '{password}';
      END IF;
    END
    $$;
    """)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app;")
    op.execute("CREATE SCHEMA IF NOT EXISTS eval;")

    pipeline_password = os.environ.get("BT_PIPELINE_PASSWORD", "devpassword")
    eval_password = os.environ.get("BT_EVAL_PASSWORD", "devpassword")

    _create_role_if_missing("bt_pipeline", pipeline_password)
    _create_role_if_missing("bt_eval", eval_password)

    # bt_pipeline: app schema only (§7.2 — API + worker never touch eval)
    op.execute("GRANT USAGE ON SCHEMA app TO bt_pipeline;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_pipeline;")

    # bt_eval: both schemas (generator writes app.events/customers/complaints
    # and eval.gold_*; eval harness reads both) (§5.4, §7.2)
    op.execute("GRANT USAGE ON SCHEMA app TO bt_eval;")
    op.execute("GRANT USAGE ON SCHEMA eval TO bt_eval;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_eval;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA eval GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bt_eval;")


def downgrade() -> None:
    op.execute("DROP OWNED BY bt_pipeline;")
    op.execute("DROP OWNED BY bt_eval;")
    op.execute("DROP ROLE IF EXISTS bt_pipeline;")
    op.execute("DROP ROLE IF EXISTS bt_eval;")
    op.execute("DROP SCHEMA IF EXISTS eval CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE;")
