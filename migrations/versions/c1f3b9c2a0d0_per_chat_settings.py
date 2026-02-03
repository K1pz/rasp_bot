"""Per-chat settings and iCal metadata.

Revision ID: c1f3b9c2a0d0
Revises: 9b7b6e4c8b1a
Create Date: 2026-01-24
"""

from alembic import op
import sqlalchemy as sa


def _column_exists(conn, table: str, column: str) -> bool:
    inspector = sa.inspect(conn)
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_map(conn, table: str) -> dict[str, dict]:
    inspector = sa.inspect(conn)
    return {idx["name"]: idx for idx in inspector.get_indexes(table)}


def _unique_map(conn, table: str) -> dict[str, dict]:
    inspector = sa.inspect(conn)
    return {uc["name"]: uc for uc in inspector.get_unique_constraints(table)}


# revision identifiers, used by Alembic.
revision = "c1f3b9c2a0d0"
down_revision = "9b7b6e4c8b1a"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    settings_cols = {col["name"] for col in sa.inspect(conn).get_columns("settings")}
    with op.batch_alter_table("settings") as batch_op:
        if "chat_id" not in settings_cols:
            batch_op.add_column(sa.Column("chat_id", sa.Integer(), nullable=True))
        if "ical_url" not in settings_cols:
            batch_op.add_column(sa.Column("ical_url", sa.Text(), nullable=True))

    if "student_chat_id" in settings_cols:
        op.execute(
            "UPDATE settings SET chat_id = student_chat_id "
            "WHERE chat_id IS NULL AND student_chat_id IS NOT NULL"
        )

    if sa.inspect(conn).has_table("uploads"):
        uploads_cols = {col["name"] for col in sa.inspect(conn).get_columns("uploads")}
        with op.batch_alter_table("uploads") as batch_op:
            if "chat_id" not in uploads_cols:
                batch_op.add_column(sa.Column("chat_id", sa.Integer(), nullable=True))

    if sa.inspect(conn).has_table("schedule_items"):
        sched_cols = {col["name"] for col in sa.inspect(conn).get_columns("schedule_items")}
        sched_indexes = _index_map(conn, "schedule_items")
        sched_uniques = _unique_map(conn, "schedule_items")

        idx_date_cols = sched_indexes.get("idx_schedule_date", {}).get("column_names")
        idx_date_start_cols = sched_indexes.get("idx_schedule_date_start", {}).get("column_names")
        idx_ical_cols = sched_indexes.get("idx_schedule_ical_key", {}).get("column_names")
        uk_ical_cols = sched_uniques.get("uq_schedule_ical_key", {}).get("column_names")

        desired_idx_date = ["chat_id", "date"]
        desired_idx_date_start = ["chat_id", "date", "start_time"]
        desired_idx_ical = ["chat_id", "ical_uid", "ical_dtstart"]

        drop_idx_date = idx_date_cols is not None and idx_date_cols != desired_idx_date
        drop_idx_date_start = idx_date_start_cols is not None and idx_date_start_cols != desired_idx_date_start
        drop_idx_ical = idx_ical_cols is not None and idx_ical_cols != desired_idx_ical

        uk_exists = "uq_schedule_ical_key" in sched_uniques
        uk_index_exists = "uq_schedule_ical_key" in sched_indexes and not uk_exists
        drop_uk = (uk_ical_cols is not None and uk_ical_cols != desired_idx_ical) or uk_index_exists
        create_uk = uk_ical_cols != desired_idx_ical

        create_idx_date = idx_date_cols != desired_idx_date
        create_idx_date_start = idx_date_start_cols != desired_idx_date_start
        create_idx_ical = idx_ical_cols != desired_idx_ical

        with op.batch_alter_table("schedule_items") as batch_op:
            if "chat_id" not in sched_cols:
                batch_op.add_column(sa.Column("chat_id", sa.Integer(), nullable=True))
            if drop_uk and uk_exists:
                batch_op.drop_constraint("uq_schedule_ical_key", type_="unique")
            if drop_uk and uk_index_exists:
                batch_op.drop_index("uq_schedule_ical_key")
            if drop_idx_date:
                batch_op.drop_index("idx_schedule_date")
            if drop_idx_date_start:
                batch_op.drop_index("idx_schedule_date_start")
            if drop_idx_ical:
                batch_op.drop_index("idx_schedule_ical_key")
            if create_idx_date:
                batch_op.create_index("idx_schedule_date", ["chat_id", "date"])
            if create_idx_date_start:
                batch_op.create_index("idx_schedule_date_start", ["chat_id", "date", "start_time"])
            if create_idx_ical:
                batch_op.create_index("idx_schedule_ical_key", ["chat_id", "ical_uid", "ical_dtstart"])
            if create_uk:
                batch_op.create_unique_constraint("uq_schedule_ical_key", ["chat_id", "ical_uid", "ical_dtstart"])

    if _column_exists(conn, "schedule_items", "chat_id") and _column_exists(conn, "settings", "chat_id"):
        op.execute(
            "UPDATE schedule_items SET chat_id = ("
            "SELECT chat_id FROM settings WHERE chat_id IS NOT NULL LIMIT 1"
            ") WHERE chat_id IS NULL"
        )
    if _column_exists(conn, "uploads", "chat_id") and _column_exists(conn, "settings", "chat_id"):
        op.execute(
            "UPDATE uploads SET chat_id = ("
            "SELECT chat_id FROM settings WHERE chat_id IS NOT NULL LIMIT 1"
            ") WHERE chat_id IS NULL"
        )


def downgrade():
    with op.batch_alter_table("schedule_items") as batch_op:
        batch_op.drop_constraint("uq_schedule_ical_key", type_="unique")
        batch_op.drop_index("idx_schedule_date")
        batch_op.drop_index("idx_schedule_date_start")
        batch_op.drop_index("idx_schedule_ical_key")
        batch_op.create_index("idx_schedule_date", ["date"])
        batch_op.create_index("idx_schedule_date_start", ["date", "start_time"])
        batch_op.create_index("idx_schedule_ical_key", ["ical_uid", "ical_dtstart"])
        batch_op.create_unique_constraint("uq_schedule_ical_key", ["ical_uid", "ical_dtstart"])
        batch_op.drop_column("chat_id")

    with op.batch_alter_table("uploads") as batch_op:
        batch_op.drop_column("chat_id")

    with op.batch_alter_table("settings") as batch_op:
        batch_op.drop_column("ical_url")
        batch_op.drop_column("chat_id")
