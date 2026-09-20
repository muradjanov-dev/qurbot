"""Mark synthetic guest accounts without fabricated Telegram IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0020_test_customers"
down_revision = "0019_visitors_operator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    raise RuntimeError("Keep test-account markers on application rollback")
