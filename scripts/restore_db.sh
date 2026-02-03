#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/bot.db.YYYYmmdd-HHMMSS.sqlite"
  exit 2
fi

BACKUP_PATH="$1"
if [[ ! -f "${BACKUP_PATH}" ]]; then
  echo "Backup file not found: ${BACKUP_PATH}"
  exit 2
fi

BACKUP_DIR="$(cd -- "$(dirname -- "${BACKUP_PATH}")" && pwd)"
BACKUP_FILE="$(basename -- "${BACKUP_PATH}")"

PRE_BACKUP_DIR="${PROJECT_ROOT}/backups"
mkdir -p "${PRE_BACKUP_DIR}"
PRE_TS="$(date +"%Y%m%d-%H%M%S")"
PRE_BACKUP_FILE="pre_restore.${PRE_TS}.sqlite"

echo "Stopping bot..."
docker compose stop bot

echo "Restoring from: ${BACKUP_DIR}/${BACKUP_FILE}"
echo "Saving current DB snapshot (if exists) to: ${PRE_BACKUP_DIR}/${PRE_BACKUP_FILE}"

docker compose run --rm --no-deps -T \
  -v "${BACKUP_DIR}:/in" \
  -v "${PRE_BACKUP_DIR}:/out" \
  -e IN_DIR=/in \
  -e IN_FILE="${BACKUP_FILE}" \
  -e OUT_DIR=/out \
  -e OUT_FILE="${PRE_BACKUP_FILE}" \
  --entrypoint python bot - <<'PY'
import os
import shutil
import sqlite3
from pathlib import Path

db_url = os.environ.get("DB_PATH", "sqlite+aiosqlite:///./data/bot.db")

def sqlite_path_from_sqla_url(url: str) -> str:
    if not url.startswith("sqlite"):
        raise SystemExit(f"DB_PATH is not sqlite: {url}")
    if url.startswith("sqlite+"):
        url = "sqlite:" + url.split(":", 1)[1]
    rest = url[len("sqlite:"):]
    rest = rest.split("?", 1)[0]
    if rest.startswith("///"):
        return rest[3:]
    return rest.lstrip("/")

db_path = Path(sqlite_path_from_sqla_url(db_url))
if not db_path.is_absolute():
    db_path = (Path.cwd() / db_path).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)

in_path = (Path(os.environ["IN_DIR"]) / os.environ["IN_FILE"]).resolve()
if not in_path.exists():
    raise SystemExit(f"Input backup not found: {in_path}")

out_path = (Path(os.environ["OUT_DIR"]) / os.environ["OUT_FILE"]).resolve()

def snapshot_current_db_if_exists() -> None:
    if not db_path.exists():
        return
    src = sqlite3.connect(str(db_path))
    try:
        src.execute("PRAGMA busy_timeout=30000;")
        try:
            src.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        dst = sqlite3.connect(str(out_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

snapshot_current_db_if_exists()

tmp_path = db_path.with_suffix(db_path.suffix + ".restore_tmp")
shutil.copy2(in_path, tmp_path)
tmp_path.replace(db_path)

for suffix in ("-wal", "-shm"):
    p = Path(str(db_path) + suffix)
    try:
        p.unlink()
    except FileNotFoundError:
        pass

conn = sqlite3.connect(str(db_path))
try:
    (result,) = conn.execute("PRAGMA integrity_check;").fetchone()
finally:
    conn.close()

if result != "ok":
    raise SystemExit(f"Integrity check failed: {result}")

print(f"OK: restored to {db_path}")
PY

echo "Starting bot..."
docker compose up -d
echo "Done."

