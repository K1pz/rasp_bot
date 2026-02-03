"""Add per-chat settings fields and de-dup markers.

Revision ID: f2b1c8d4a9e7
Revises: c1f3b9c2a0d0
Create Date: 2026-01-24
"""

from alembic import op
import sqlalchemy as sa


def _column_exists(conn, table: str, column: str) -> bool:
    inspector = sa.inspect(conn)
    return any(col["name"] == column for col in inspector.get_columns(table))


def _unique_exists(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    uniques = inspector.get_unique_constraints(table)
    if any(uc["name"] == name for uc in uniques):
        return True
    return any(idx["name"] == name for idx in inspector.get_indexes(table))


# revision identifiers, used by Alembic.
revision = "f2b1c8d4a9e7"
down_revision = "c1f3b9c2a0d0"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    with op.batch_alter_table("settings") as batch_op:
        if not _column_exists(conn, "settings", "chat_title"):
            batch_op.add_column(sa.Column("chat_title", sa.Text(), nullable=True))
        if not _column_exists(conn, "settings", "last_ical_sync_at"):
            batch_op.add_column(sa.Column("last_ical_sync_at", sa.Text(), nullable=True))
        if not _column_exists(conn, "settings", "coverage_end_date"):
            batch_op.add_column(sa.Column("coverage_end_date", sa.Text(), nullable=True))
        if not _column_exists(conn, "settings", "last_sent_morning_date"):
            batch_op.add_column(sa.Column("last_sent_morning_date", sa.Text(), nullable=True))
        if not _column_exists(conn, "settings", "last_sent_evening_date"):
            batch_op.add_column(sa.Column("last_sent_evening_date", sa.Text(), nullable=True))
        if not _column_exists(conn, "settings", "last_sent_manual_at"):
            batch_op.add_column(sa.Column("last_sent_manual_at", sa.Text(), nullable=True))
        if not _unique_exists(conn, "settings", "uq_settings_chat_id"):
            batch_op.create_unique_constraint("uq_settings_chat_id", ["chat_id"])


def downgrade():
    conn = op.get_bind()
    with op.batch_alter_table("settings") as batch_op:
        if _unique_exists(conn, "settings", "uq_settings_chat_id"):
            batch_op.drop_constraint("uq_settings_chat_id", type_="unique")
        if _column_exists(conn, "settings", "last_sent_manual_at"):
            batch_op.drop_column("last_sent_manual_at")
        if _column_exists(conn, "settings", "last_sent_evening_date"):
            batch_op.drop_column("last_sent_evening_date")
        if _column_exists(conn, "settings", "last_sent_morning_date"):
            batch_op.drop_column("last_sent_morning_date")
        if _column_exists(conn, "settings", "coverage_end_date"):
            batch_op.drop_column("coverage_end_date")
        if _column_exists(conn, "settings", "last_ical_sync_at"):
            batch_op.drop_column("last_ical_sync_at")
        if _column_exists(conn, "settings", "chat_title"):
            batch_op.drop_column("chat_title")
