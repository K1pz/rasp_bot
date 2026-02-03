"""Enforce per-chat settings PK and add chat_id FKs.

Revision ID: 5a1d6e7b2c9f
Revises: 7c1b2a9d4f10
Create Date: 2026-01-25
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a1d6e7b2c9f"
down_revision = "7c1b2a9d4f10"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    inspector = sa.inspect(conn)
    return name in inspector.get_table_names()


def _column_exists(conn, table: str, column: str) -> bool:
    inspector = sa.inspect(conn)
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_exists(conn, table: str, name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(idx["name"] == name for idx in inspector.get_indexes(table))


def _get_default_chat_id(conn) -> int | None:
    if _column_exists(conn, "settings", "student_chat_id"):
        val = conn.execute(
            sa.text(
                "SELECT student_chat_id FROM settings "
                "WHERE student_chat_id IS NOT NULL LIMIT 1"
            )
        ).scalar()
        if val is not None:
            return val
    return conn.execute(
        sa.text(
            "SELECT chat_id FROM send_log "
            "GROUP BY chat_id ORDER BY COUNT(*) DESC LIMIT 1"
        )
    ).scalar()


def upgrade():
    conn = op.get_bind()
    if not _table_exists(conn, "settings"):
        return

    existing_settings_cols = {col["name"] for col in sa.inspect(conn).get_columns("settings")}
    has_ical_enabled = "ical_enabled" in existing_settings_cols

    default_chat_id = None

    null_settings = conn.execute(
        sa.text("SELECT 1 FROM settings WHERE chat_id IS NULL LIMIT 1")
    ).scalar()
    if null_settings:
        default_chat_id = _get_default_chat_id(conn)
        if default_chat_id is None:
            raise RuntimeError(
                "settings.chat_id has NULLs, but no default chat_id could be derived "
                "from settings.student_chat_id or send_log. Populate chat_id and retry."
            )
        conn.execute(
            sa.text("UPDATE settings SET chat_id = :cid WHERE chat_id IS NULL"),
            {"cid": default_chat_id},
        )

    for table in ("schedule_items", "uploads"):
        if not _table_exists(conn, table):
            continue
        has_nulls = conn.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE chat_id IS NULL LIMIT 1")
        ).scalar()
        if has_nulls:
            if default_chat_id is None:
                default_chat_id = _get_default_chat_id(conn)
            if default_chat_id is None:
                raise RuntimeError(
                    f"{table}.chat_id has NULLs, but no default chat_id could be derived "
                    "from settings.student_chat_id or send_log. Populate chat_id and retry."
                )
            conn.execute(
                sa.text(f"UPDATE {table} SET chat_id = :cid WHERE chat_id IS NULL"),
                {"cid": default_chat_id},
            )

    now = datetime.utcnow().isoformat()
    if _table_exists(conn, "schedule_items") or _table_exists(conn, "uploads"):
        conn.execute(
            sa.text(
                "INSERT INTO settings (chat_id, mode, morning_time, timezone, updated_at) "
                "SELECT chat_id, 0, '07:00', 'Europe/Moscow', :now FROM ("
                "SELECT DISTINCT chat_id FROM schedule_items WHERE chat_id IS NOT NULL "
                "UNION "
                "SELECT DISTINCT chat_id FROM uploads WHERE chat_id IS NOT NULL"
                ") AS ids "
                "WHERE chat_id NOT IN (SELECT chat_id FROM settings)"
            ),
            {"now": now},
        )

    settings_new_args = [
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("chat_title", sa.Text(), nullable=True),
        sa.Column("ical_url", sa.Text(), nullable=True),
    ]
    if has_ical_enabled:
        settings_new_args.append(
            sa.Column("ical_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )
    settings_new_args.extend(
        [
            sa.Column("mode", sa.Integer(), nullable=False),
            sa.Column("morning_time", sa.Text(), nullable=True),
            sa.Column("evening_time", sa.Text(), nullable=True),
            sa.Column("timezone", sa.Text(), nullable=False),
            sa.Column("last_ical_sync_at", sa.Text(), nullable=True),
            sa.Column("coverage_end_date", sa.Text(), nullable=True),
            sa.Column("last_sent_morning_date", sa.Text(), nullable=True),
            sa.Column("last_sent_evening_date", sa.Text(), nullable=True),
            sa.Column("last_sent_manual_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.CheckConstraint("mode IN (0, 1, 2)", name="ck_settings_mode"),
            sa.PrimaryKeyConstraint("chat_id"),
        ]
    )
    op.create_table("settings_new", *settings_new_args)

    ical_enabled_insert = "ical_enabled, " if has_ical_enabled else ""
    ical_enabled_select = "COALESCE(ical_enabled, 1), " if has_ical_enabled else ""
    conn.execute(
        sa.text(
            "INSERT INTO settings_new ("
            "chat_id, chat_title, ical_url, "
            f"{ical_enabled_insert}"
            "mode, morning_time, evening_time, timezone, "
            "last_ical_sync_at, coverage_end_date, last_sent_morning_date, "
            "last_sent_evening_date, last_sent_manual_at, updated_at"
            ") "
            "SELECT chat_id, chat_title, ical_url, "
            f"{ical_enabled_select}"
            "COALESCE(mode, 0), morning_time, evening_time, "
            "COALESCE(timezone, 'Europe/Moscow'), last_ical_sync_at, coverage_end_date, "
            "last_sent_morning_date, last_sent_evening_date, last_sent_manual_at, "
            "COALESCE(updated_at, :now) "
            "FROM settings"
        ),
        {"now": now},
    )

    op.drop_table("settings")
    op.rename_table("settings_new", "settings")

    with op.batch_alter_table("schedule_items", recreate="always") as batch_op:
        batch_op.alter_column("chat_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_schedule_items_chat_id_settings",
            "settings",
            ["chat_id"],
            ["chat_id"],
        )

    with op.batch_alter_table("uploads", recreate="always") as batch_op:
        batch_op.alter_column("chat_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_uploads_chat_id_settings",
            "settings",
            ["chat_id"],
            ["chat_id"],
        )

    if _table_exists(conn, "setup_tokens") and not _index_exists(
        conn, "setup_tokens", "idx_setup_tokens_expires_at"
    ):
        op.create_index(
            "idx_setup_tokens_expires_at",
            "setup_tokens",
            ["expires_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("schedule_items", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_schedule_items_chat_id_settings", type_="foreignkey")
        batch_op.alter_column("chat_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("uploads", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_uploads_chat_id_settings", type_="foreignkey")
        batch_op.alter_column("chat_id", existing_type=sa.Integer(), nullable=True)

    op.drop_index("idx_setup_tokens_expires_at", table_name="setup_tokens")

    op.create_table(
        "settings_old",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_chat_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("chat_title", sa.Text(), nullable=True),
        sa.Column("ical_url", sa.Text(), nullable=True),
        sa.Column("mode", sa.Integer(), nullable=False),
        sa.Column("morning_time", sa.Text(), nullable=False),
        sa.Column("evening_time", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("last_ical_sync_at", sa.Text(), nullable=True),
        sa.Column("coverage_end_date", sa.Text(), nullable=True),
        sa.Column("last_sent_morning_date", sa.Text(), nullable=True),
        sa.Column("last_sent_evening_date", sa.Text(), nullable=True),
        sa.Column("last_sent_manual_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_settings_chat_id"),
    )

    conn = op.get_bind()
    now = datetime.utcnow().isoformat()
    conn.execute(
        sa.text(
            "INSERT INTO settings_old ("
            "student_chat_id, chat_id, chat_title, ical_url, mode, morning_time, "
            "evening_time, timezone, last_ical_sync_at, coverage_end_date, "
            "last_sent_morning_date, last_sent_evening_date, last_sent_manual_at, updated_at"
            ") "
            "SELECT NULL, chat_id, chat_title, ical_url, "
            "COALESCE(mode, 0), COALESCE(morning_time, '07:00'), evening_time, "
            "COALESCE(timezone, 'Europe/Moscow'), last_ical_sync_at, coverage_end_date, "
            "last_sent_morning_date, last_sent_evening_date, last_sent_manual_at, "
            "COALESCE(updated_at, :now) "
            "FROM settings"
        ),
        {"now": now},
    )

    op.drop_table("settings")
    op.rename_table("settings_old", "settings")
