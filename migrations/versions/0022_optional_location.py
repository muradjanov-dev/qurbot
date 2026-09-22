"""Allow typed saved addresses and attach an optional pin to sales requests."""

import sqlalchemy as sa
from alembic import op

revision = "0022_optional_location"
down_revision = "0021_sales_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("user_addresses", "lat", existing_type=sa.Numeric(10, 7), nullable=True)
    op.alter_column("user_addresses", "lng", existing_type=sa.Numeric(10, 7), nullable=True)
    op.add_column("sales_requests", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("sales_requests", sa.Column("lng", sa.Numeric(10, 7), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_requests", "lng")
    op.drop_column("sales_requests", "lat")
    # Existing text-only saved addresses cannot be assigned a truthful pin.
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM user_addresses WHERE lat IS NULL"))
    if count:
        raise RuntimeError("Text-only saved addresses must be removed before downgrade")
    op.alter_column("user_addresses", "lng", existing_type=sa.Numeric(10, 7), nullable=False)
    op.alter_column("user_addresses", "lat", existing_type=sa.Numeric(10, 7), nullable=False)
