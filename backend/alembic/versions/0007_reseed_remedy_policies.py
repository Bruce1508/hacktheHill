"""Re-assert the two canonical remedy_policies rows seeded by 0006. Earlier
test runs merged over and then deleted 'policy-outage-credit-v1'; this is a
no-op where the rows survived and a repair where they didn't."""
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO app.remedy_policies (id, rule_type, config, version) VALUES
        ('policy-outage-credit-v1', 'outage_credit', '{"price_table": {"fiber_basic": 2.00, "fiber_pro": 3.50, "tv_bundle": 4.75, "business_ethernet": 12.00}}', 1),
        ('policy-overcharge-refund-v1', 'overcharge_refund', '{"goodwill_amount": 15.00}', 1)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    pass  # the rows belong to 0006; nothing to undo here
