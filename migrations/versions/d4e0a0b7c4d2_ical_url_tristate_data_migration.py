"""iCal URL tri-state: preserve NULL as "unset"

Revision ID: d4e0a0b7c4d2
Revises: f2b1c8d4a9e7
Create Date: 2026-01-30
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d4e0a0b7c4d2"
down_revision = "f2b1c8d4a9e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    We keep a 3-state iCal behavior per chat:
    - Explicit URL: use it.
    - Unset (ical_enabled=True, ical_url is NULL/empty): may fall back to env default.
    - Disabled (ical_enabled=False): never use iCal even if env default exists.

    Historical databases may have settings.ical_url as NULL or empty. We interpret it as
    "unset" to keep predictable behavior with env defaults.
    """
    # Normalize empty strings/whitespace to NULL (unset).
    op.execute("UPDATE settings SET ical_url=NULL WHERE trim(COALESCE(ical_url, ''))=''")


def downgrade() -> None:
    # No reliable way to restore prior meaning of NULL vs empty string; keep as-is.
    pass
