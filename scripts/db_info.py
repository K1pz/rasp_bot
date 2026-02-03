#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def _sqlite_path_from_sqla_url(url: str) -> Path:
    if not url.startswith("sqlite"):
        raise ValueError(f"DB_PATH is not sqlite: {url}")
    if url.startswith("sqlite+"):
        # sqlite+aiosqlite:///... -> sqlite:///...
        url = "sqlite:" + url.split(":", 1)[1]
    rest = url[len("sqlite:") :]
    rest = rest.split("?", 1)[0]
    if rest.startswith("///"):
        return Path(rest[3:])
    return Path(rest.lstrip("/"))


def main() -> int:
    db_url = os.environ.get("DB_PATH", "sqlite+aiosqlite:///./data/bot.db")
    try:
        db_path = _sqlite_path_from_sqla_url(db_url)
    except Exception as exc:
        print(f"ERROR: failed to parse DB_PATH={db_url!r}: {exc}", file=sys.stderr)
        return 2

    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()

    print(f"DB_PATH={db_url}")
    print(f"SQLite file={db_path} (exists={db_path.exists()})")
    if not db_path.exists():
        print("WARN: DB file not found. If this is not a first run, check your volume mount.", file=sys.stderr)
        return 1

    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA busy_timeout=30000;")
        journal_mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
        settings_count = con.execute("SELECT COUNT(*) FROM settings;").fetchone()[0]
        print(f"journal_mode={journal_mode}")
        print(f"settings_rows={settings_count}")
        if settings_count == 0:
            print(
                "WARN: settings table is empty. If you expected existing config, the bot likely started with a new/empty DB.",
                file=sys.stderr,
            )
        else:
            rows = con.execute(
                "SELECT chat_id, COALESCE(chat_title, ''), COALESCE(ical_url, ''), ical_enabled, updated_at "
                "FROM settings ORDER BY updated_at DESC LIMIT 5;"
            ).fetchall()
            for chat_id, chat_title, ical_url, ical_enabled, updated_at in rows:
                title = chat_title if chat_title else "-"
                url = ical_url if ical_url else "-"
                print(f"row: chat_id={chat_id} title={title!r} ical_enabled={int(ical_enabled)} ical_url={url!r} updated_at={updated_at}")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

