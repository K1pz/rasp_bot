import asyncio
import errno
import logging
import os
from pathlib import Path
import shutil
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from app.config import settings

SQLITE_TIMEOUT_SECONDS = 30


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def sqlite_db_file_path(db_url: str) -> Path | None:
    if not _is_sqlite_url(db_url):
        return None
    try:
        url = make_url(db_url)
    except Exception:
        return None

    db = getattr(url, "database", None)
    if not db or db == ":memory:":
        return None
    return Path(db)

def _resolve_db_path(db_path: Path, cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    if db_path.is_absolute():
        return db_path.resolve()
    return (cwd / db_path).resolve()


def _fsync_dir_best_effort(directory: Path) -> None:
    try:
        fd = os.open(str(directory), getattr(os, "O_RDONLY", 0))
    except Exception:
        return
    try:
        try:
            os.fsync(fd)
        except Exception:
            pass
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def _copy_file_with_fsync(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as r, open(dst, "xb") as w:
        shutil.copyfileobj(r, w, length=1024 * 1024)
        w.flush()
        os.fsync(w.fileno())
    _fsync_dir_best_effort(dst.parent)


def _directory_write_check(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f".writecheck-{uuid.uuid4().hex}"
    try:
        with open(tmp, "xb") as f:
            f.write(b"1")
            f.flush()
            os.fsync(f.fileno())
        tmp.unlink(missing_ok=True)
        _fsync_dir_best_effort(directory)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _backup_path_for(old_db: Path) -> Path:
    candidate = old_db.with_name(f"{old_db.name}.bak")
    if not candidate.exists():
        return candidate
    suffix = uuid.uuid4().hex[:8]
    return old_db.with_name(f"{old_db.name}.bak.{suffix}")


def soft_migrate_sqlite_db_file(old_db: Path, new_db: Path) -> bool:
    """
    Soft-migrate an SQLite DB file from old_db to new_db.

    Rules:
    - If new_db exists: do nothing.
    - If old_db doesn't exist: do nothing.
    - If new_db doesn't exist and old_db exists: try atomic move; fallback to copy+fsync.
      On copy success, keep old_db as a backup (rename to *.bak* best-effort).
    """
    old_db = old_db.resolve()
    new_db = new_db.resolve()

    if new_db.exists():
        logging.info("SQLite migration not required: new DB exists (%s)", new_db)
        return False
    if not old_db.exists():
        logging.info("SQLite migration not required: old DB not found (%s)", old_db)
        return False
    if old_db == new_db:
        logging.info("SQLite migration not required: DB path unchanged (%s)", new_db)
        return False

    new_db.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.replace(old_db, new_db)
        _fsync_dir_best_effort(new_db.parent)
        logging.info("SQLite migrated (move): %s -> %s", old_db, new_db)
        return True
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EACCES, errno.EPERM, errno.EROFS):
            logging.info("SQLite move failed; falling back to copy: %s", exc)
        else:
            logging.info("SQLite move not possible; using copy instead: %s", exc)

    try:
        _copy_file_with_fsync(old_db, new_db)
    except Exception:
        logging.exception("SQLite migration (copy) failed: %s -> %s", old_db, new_db)
        return False

    try:
        backup = _backup_path_for(old_db)
        os.replace(old_db, backup)
        _fsync_dir_best_effort(backup.parent)
        logging.info("SQLite old DB kept as backup: %s", backup)
    except Exception:
        logging.exception("SQLite backup rename failed; leaving old DB in place (%s)", old_db)

    logging.info("SQLite migrated (copy): %s -> %s", old_db, new_db)
    return True


def _prepare_sqlite_filesystem(db_url: str) -> None:
    sqlite_db = sqlite_db_file_path(db_url)
    if sqlite_db is None:
        return

    new_db_abs = _resolve_db_path(sqlite_db)
    old_db_abs = (Path.cwd() / "data" / "bot.db").resolve()

    try:
        new_db_abs.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        if new_db_abs.exists():
            logging.exception("Failed to create DB directory, but DB exists: %s", new_db_abs.parent)
        else:
            logging.exception("Failed to create DB directory: %s", new_db_abs.parent)
            raise

    try:
        _directory_write_check(new_db_abs.parent)
    except Exception:
        msg = (
            f"Directory {new_db_abs.parent} is not writable; "
            "on Railway try RAILWAY_RUN_UID=0 or check volume mount"
        )
        if new_db_abs.exists():
            logging.exception("%s (DB exists at %s; continuing)", msg, new_db_abs)
        else:
            logging.exception("%s (DB does not exist; cannot create %s)", msg, new_db_abs)
            raise RuntimeError(msg)

    # Soft migrate old default location -> new DB path (only when new doesn't exist yet).
    try:
        soft_migrate_sqlite_db_file(old_db_abs, new_db_abs)
    except Exception:
        logging.exception("SQLite migration failed unexpectedly (%s -> %s)", old_db_abs, new_db_abs)


_engine = None
_session_maker = None


def _ensure_engine_initialized() -> None:
    global _engine, _session_maker
    if _engine is not None and _session_maker is not None:
        return

    _prepare_sqlite_filesystem(settings.DB_PATH)

    connect_args = {"timeout": SQLITE_TIMEOUT_SECONDS} if _is_sqlite_url(settings.DB_PATH) else {}
    _engine = create_async_engine(settings.DB_PATH, echo=False, connect_args=connect_args)
    _session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def async_session_maker() -> AsyncSession:
    _ensure_engine_initialized()
    assert _session_maker is not None
    return _session_maker()

# Enable foreign_keys = ON (sqlite specific)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if not _is_sqlite_url(settings.DB_PATH):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_TIMEOUT_SECONDS * 1000}")
    finally:
        cursor.close()

def get_engine():
    _ensure_engine_initialized()
    assert _engine is not None
    return _engine


async def ensure_schema() -> None:
    """
    Ensure the database schema matches the latest migrations.
    """
    _ensure_engine_initialized()
    try:
        db_url = make_url(settings.DB_PATH).render_as_string(hide_password=True)
    except Exception:
        db_url = settings.DB_PATH
    logging.info("Database URL=%s", db_url)

    sqlite_db = sqlite_db_file_path(settings.DB_PATH)
    if sqlite_db is not None:
        sqlite_db_abs = _resolve_db_path(sqlite_db)
        logging.info("SQLite DB file=%s (exists=%s)", sqlite_db_abs, sqlite_db_abs.exists())
    try:
        await asyncio.to_thread(_run_migrations)
    except Exception:
        logging.exception("Database migrations failed")
        raise


def _run_migrations() -> None:
    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DB_PATH)
    command.upgrade(alembic_cfg, "head")
