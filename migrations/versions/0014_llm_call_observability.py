"""Add non-breaking LLM matching observability fields.

Revision ID: 0014_llm_call_observability
Revises: 0013_delivery_policy
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_llm_call_observability"
down_revision: str | None = "0013_delivery_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("model", sa.String(length=100), nullable=True))
    op.add_column("llm_calls", sa.Column("outcome", sa.String(length=32), nullable=True))
    op.add_column("llm_calls", sa.Column("attempt_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_calls", "attempt_count")
    op.drop_column("llm_calls", "outcome")
    op.drop_column("llm_calls", "model")
