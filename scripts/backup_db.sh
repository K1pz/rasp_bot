#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

BACKUP_DIR="${1:-${PROJECT_ROOT}/backups}"
mkdir -p "${BACKUP_DIR}"

TS="$(date +"%Y%m%d-%H%M%S")"
BACKUP_FILE="bot.db.${TS}.sqlite"

echo "Creating backup: ${BACKUP_DIR}/${BACKUP_FILE}"

# Create a consistent SQLite snapshot using the built-in backup API.
# This works correctly with WAL mode enabled (no need to copy -wal/-shm).
docker compose run --rm --no-deps -T \
  -v "${BACKUP_DIR}:/backup" \
  -e BACKUP_DIR=/backup \
  -e BACKUP_FILE="${BACKUP_FILE}" \
  --entrypoint python bot - <<'PY'
import os
import sqlite3
from pathlib import Path

db_url = os.environ.get("DB_PATH", "sqlite+aiosqlite:///./data/bot.db")

def sqlite_path_from_sqla_url(url: str) -> str:
    if not url.startswith("sqlite"):
        raise SystemExit(f"DB_PATH is not sqlite: {url}")
    if url.startswith("sqlite+"):
        # sqlite+aiosqlite:///... -> sqlite:///...
        url = "sqlite:" + url.split(":", 1)[1]
    rest = url[len("sqlite:"):]
    rest = rest.split("?", 1)[0]
    if rest.startswith("///"):
        return rest[3:]
    return rest.lstrip("/")

db_path = Path(sqlite_path_from_sqla_url(db_url))
if not db_path.is_absolute():
    db_path = (Path.cwd() / db_path).resolve()

if not db_path.exists():
    raise SystemExit(f"DB file does not exist: {db_path}")

backup_dir = Path(os.environ["BACKUP_DIR"])
backup_file = os.environ["BACKUP_FILE"]
dst_path = (backup_dir / backup_file).resolve()
backup_dir.mkdir(parents=True, exist_ok=True)

src = sqlite3.connect(str(db_path))
try:
    src.execute("PRAGMA busy_timeout=30000;")
    try:
        # Try to checkpoint WAL to reduce WAL growth; ignore if not supported.
        src.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass

    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
finally:
    src.close()

print(f"OK: {dst_path}")
PY

