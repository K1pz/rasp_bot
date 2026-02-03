import asyncio
import logging
from pathlib import Path

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


def _sqlite_db_file_path(db_url: str) -> Path | None:
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

# 3.1) Create SQLAlchemy async engine
_connect_args = {"timeout": SQLITE_TIMEOUT_SECONDS} if _is_sqlite_url(settings.DB_PATH) else {}
engine = create_async_engine(settings.DB_PATH, echo=False, connect_args=_connect_args)

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

# Create sessionmaker
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def ensure_schema() -> None:
    """
    Ensure the database schema matches the latest migrations.
    """
    try:
        db_url = make_url(settings.DB_PATH).render_as_string(hide_password=True)
    except Exception:
        db_url = settings.DB_PATH
    logging.info("DB_PATH=%s", db_url)

    sqlite_db = _sqlite_db_file_path(settings.DB_PATH)
    if sqlite_db is not None:
        sqlite_db_abs = sqlite_db if sqlite_db.is_absolute() else (Path.cwd() / sqlite_db).resolve()
        logging.info("SQLite DB file=%s (exists=%s)", sqlite_db_abs, sqlite_db_abs.exists())
        sqlite_db_abs.parent.mkdir(parents=True, exist_ok=True)
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
