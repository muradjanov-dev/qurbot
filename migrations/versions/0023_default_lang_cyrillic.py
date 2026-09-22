"""Lead with Uzbek Cyrillic for accounts that never chose a script.

`users.lang` is NOT NULL with a server default, so every existing row already
carries a value and there is no way to tell "picked Latin" apart from "was
given the old default". Rewriting them would silently change the language of
customers who chose Latin on purpose, so this revision only moves the default
for rows created from now on. Anyone can still switch from Settings.

Revision ID: 0023_default_lang_cyrillic
Revises: 0022_optional_location
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_default_lang_cyrillic"
down_revision: str | None = "0022_optional_location"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "lang",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="uz_cyrl",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "lang",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="uz_latn",
    )
