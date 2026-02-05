from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from app.config import DEFAULT_DB_PATH, normalize_db_path
from app.db.connection import soft_migrate_sqlite_db_file


def test_normalize_db_path_defaults_when_empty() -> None:
    assert normalize_db_path("") == DEFAULT_DB_PATH


def test_normalize_db_path_keeps_sqlalchemy_url() -> None:
    url = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    assert normalize_db_path(url) == url


def test_normalize_db_path_converts_memory_sqlite() -> None:
    assert normalize_db_path(":memory:") == "sqlite+aiosqlite:///:memory:"


def test_normalize_db_path_converts_relative_path() -> None:
    assert normalize_db_path("data/bot.db") == "sqlite+aiosqlite:///data/bot.db"


def test_normalize_db_path_converts_absolute_path() -> None:
    if os.name == "nt":
        assert (
            normalize_db_path(r"C:\temp\bot.db")
            == "sqlite+aiosqlite:///C:/temp/bot.db"
        )
    else:
        assert normalize_db_path("/tmp/bot.db") == "sqlite+aiosqlite:////tmp/bot.db"


def test_soft_migrate_moves_when_possible(tmp_path: Path) -> None:
    old_db = tmp_path / "old.db"
    new_db = tmp_path / "new.db"
    old_db.write_bytes(b"sqlite-data")

    migrated = soft_migrate_sqlite_db_file(old_db, new_db)
    assert migrated is True
    assert new_db.exists()
    assert new_db.read_bytes() == b"sqlite-data"
    assert not old_db.exists()


def test_soft_migrate_noop_when_new_exists(tmp_path: Path) -> None:
    old_db = tmp_path / "old.db"
    new_db = tmp_path / "new.db"
    old_db.write_bytes(b"old")
    new_db.write_bytes(b"new")

    migrated = soft_migrate_sqlite_db_file(old_db, new_db)
    assert migrated is False
    assert old_db.read_bytes() == b"old"
    assert new_db.read_bytes() == b"new"


def test_soft_migrate_copy_fallback_and_backup(monkeypatch, tmp_path: Path) -> None:
    import app.db.connection as conn

    old_db = tmp_path / "bot.db"
    new_db = tmp_path / "migrated.db"
    old_db.write_bytes(b"payload")

    orig_replace = conn.os.replace

    def fake_replace(src, dst):
        src_p = Path(src).resolve()
        dst_p = Path(dst).resolve()
        if src_p == old_db.resolve() and dst_p == new_db.resolve():
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return orig_replace(src, dst)

    monkeypatch.setattr(conn.os, "replace", fake_replace)

    migrated = soft_migrate_sqlite_db_file(old_db, new_db)
    assert migrated is True
    assert new_db.read_bytes() == b"payload"
    assert not old_db.exists()

    backups = list(tmp_path.glob("bot.db.bak*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"payload"

