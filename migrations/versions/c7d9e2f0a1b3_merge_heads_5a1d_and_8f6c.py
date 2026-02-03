"""Merge heads: settings PK/FKs + per-chat iCal enabled

Revision ID: c7d9e2f0a1b3
Revises: 5a1d6e7b2c9f, 8f6c2d1a9b3e
Create Date: 2026-01-30
"""


# revision identifiers, used by Alembic.
revision = "c7d9e2f0a1b3"
down_revision = ("5a1d6e7b2c9f", "8f6c2d1a9b3e")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge revision: no schema changes.
    pass


def downgrade() -> None:
    pass

