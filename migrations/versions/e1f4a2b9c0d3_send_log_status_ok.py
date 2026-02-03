"""Send log: use ok/error statuses

Revision ID: e1f4a2b9c0d3
Revises: c7d9e2f0a1b3
Create Date: 2026-01-30
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "e1f4a2b9c0d3"
down_revision = "c7d9e2f0a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy rows used "sent" for success; normalize to "ok".
    op.execute("UPDATE send_log SET status='ok' WHERE status='sent'")


def downgrade() -> None:
    op.execute("UPDATE send_log SET status='sent' WHERE status='ok'")

