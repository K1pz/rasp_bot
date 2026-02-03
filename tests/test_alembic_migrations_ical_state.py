from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings as env_settings


def _alembic_cfg(repo_root: Path) -> Config:
    return Config(str(repo_root / "alembic.ini"))


def test_alembic_migration_ical_null_is_unset_and_dash_is_disabled(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    db_file = tmp_path / "migrations_ical.db"

    db_url = f"sqlite+aiosqlite:///{db_file.resolve().as_posix()}"
    monkeypatch.setattr(env_settings, "DB_PATH", db_url, raising=False)

    cfg = _alembic_cfg(repo_root)

    # Create schema as it existed before the iCal tri-state + enabled flag.
    command.upgrade(cfg, "f2b1c8d4a9e7")

    con = sqlite3.connect(db_file)
    try:
        con.execute(
            """
            INSERT INTO settings (student_chat_id, chat_id, chat_title, ical_url, mode, morning_time, evening_time, timezone, updated_at)
            VALUES (NULL, ?, NULL, NULL, 0, '07:00', NULL, 'UTC', '2026-01-01T00:00:00')
            """,
            (1001,),
        )
        con.execute(
            """
            INSERT INTO settings (student_chat_id, chat_id, chat_title, ical_url, mode, morning_time, evening_time, timezone, updated_at)
            VALUES (NULL, ?, NULL, '-', 0, '07:00', NULL, 'UTC', '2026-01-01T00:00:00')
            """,
            (1002,),
        )
        con.commit()
    finally:
        con.close()

    # Upgrade to latest: should keep NULL as "unset", but treat "-" as explicitly disabled.
    command.upgrade(cfg, "head")

    con = sqlite3.connect(db_file)
    try:
        row_unset = con.execute(
            "SELECT chat_id, ical_url, ical_enabled FROM settings WHERE chat_id=?",
            (1001,),
        ).fetchone()
        assert row_unset == (1001, None, 1)

        row_disabled = con.execute(
            "SELECT chat_id, ical_url, ical_enabled FROM settings WHERE chat_id=?",
            (1002,),
        ).fetchone()
        assert row_disabled == (1002, None, 0)
    finally:
        con.close()

