"""Add per-chat iCal enabled flag

Revision ID: 8f6c2d1a9b3e
Revises: d4e0a0b7c4d2
Create Date: 2026-01-30
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f6c2d1a9b3e"
down_revision = "d4e0a0b7c4d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("ical_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )

    # Legacy state migration:
    # - previous tri-state used settings.ical_url == '-' as "explicitly disabled"
    # - new model uses settings.ical_enabled == 0 and stores ical_url as NULL
    op.execute("UPDATE settings SET ical_enabled=0, ical_url=NULL WHERE trim(ical_url)='-'")


def downgrade() -> None:
    # Restore legacy disabled marker where it was explicitly disabled.
    op.execute("UPDATE settings SET ical_url='-' WHERE ical_enabled=0 AND ical_url IS NULL")
    op.drop_column("settings", "ical_enabled")

