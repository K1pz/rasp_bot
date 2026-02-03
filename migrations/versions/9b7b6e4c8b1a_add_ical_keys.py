"""add ical keys to schedule items

Revision ID: 9b7b6e4c8b1a
Revises: 22a3b527b18e
Create Date: 2026-01-24 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def _column_exists(conn, table: str, column: str) -> bool:
    inspector = sa.inspect(conn)
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_exists(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(idx["name"] == name for idx in inspector.get_indexes(table))


def _unique_exists(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    uniques = inspector.get_unique_constraints(table)
    if any(uc["name"] == name for uc in uniques):
        return True
    return any(idx["name"] == name for idx in inspector.get_indexes(table))


def _unique_is_constraint(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    uniques = inspector.get_unique_constraints(table)
    return any(uc["name"] == name for uc in uniques)


# revision identifiers, used by Alembic.
revision: str = "9b7b6e4c8b1a"
down_revision: Union[str, Sequence[str], None] = "22a3b527b18e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    if not _column_exists(conn, "schedule_items", "ical_uid"):
        op.add_column("schedule_items", sa.Column("ical_uid", sa.Text(), nullable=True))
    if not _column_exists(conn, "schedule_items", "ical_dtstart"):
        op.add_column("schedule_items", sa.Column("ical_dtstart", sa.Text(), nullable=True))
    if not _index_exists(conn, "schedule_items", "idx_schedule_ical_key"):
        op.create_index(
            "idx_schedule_ical_key",
            "schedule_items",
            ["ical_uid", "ical_dtstart"],
            unique=False,
        )
    if not _unique_exists(conn, "schedule_items", "uq_schedule_ical_key"):
        if conn.dialect.name == "sqlite":
            op.create_index(
                "uq_schedule_ical_key",
                "schedule_items",
                ["ical_uid", "ical_dtstart"],
                unique=True,
            )
        else:
            op.create_unique_constraint(
                "uq_schedule_ical_key",
                "schedule_items",
                ["ical_uid", "ical_dtstart"],
            )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if _unique_exists(conn, "schedule_items", "uq_schedule_ical_key"):
        if _unique_is_constraint(conn, "schedule_items", "uq_schedule_ical_key"):
            op.drop_constraint("uq_schedule_ical_key", "schedule_items", type_="unique")
        else:
            op.drop_index("uq_schedule_ical_key", table_name="schedule_items")
    if _index_exists(conn, "schedule_items", "idx_schedule_ical_key"):
        op.drop_index("idx_schedule_ical_key", table_name="schedule_items")
    if _column_exists(conn, "schedule_items", "ical_dtstart"):
        op.drop_column("schedule_items", "ical_dtstart")
    if _column_exists(conn, "schedule_items", "ical_uid"):
        op.drop_column("schedule_items", "ical_uid")
