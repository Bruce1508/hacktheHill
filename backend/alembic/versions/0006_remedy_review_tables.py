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
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
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
