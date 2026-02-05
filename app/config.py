from datetime import datetime
from pathlib import Path
import re
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_DB_PATH = "sqlite+aiosqlite:///./data/bot.db"

_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[a-zA-Z]:[\\\\/]")


def _looks_like_sqlalchemy_url(value: str) -> bool:
    value = value.strip()
    if _WINDOWS_DRIVE_PATH_RE.match(value):
        return False
    return _URL_SCHEME_RE.match(value) is not None


def _sqlite_aiosqlite_url_from_path(value: str) -> str:
    value = value.strip()
    if value == ":memory:":
        return "sqlite+aiosqlite:///:memory:"

    path = Path(value).expanduser()
    path_posix = path.as_posix()

    # Windows absolute paths need: sqlite+aiosqlite:///C:/...
    if path.drive:
        return f"sqlite+aiosqlite:///{path_posix}"

    # Unix absolute paths need: sqlite+aiosqlite:////abs/path.db
    if path.is_absolute():
        return f"sqlite+aiosqlite:////{path_posix.lstrip('/')}"

    # Relative paths need: sqlite+aiosqlite:///relative/path.db
    return f"sqlite+aiosqlite:///{path_posix}"


def normalize_db_path(value: str) -> str:
    """
    Normalize DB_PATH into a SQLAlchemy URL.

    - If DB_PATH already looks like a SQLAlchemy URL (sqlite:/postgres:/...), keep as-is.
    - If DB_PATH looks like a filesystem path, convert it to sqlite+aiosqlite URL.
    """
    value = (value or "").strip()
    if not value:
        return DEFAULT_DB_PATH
    if _looks_like_sqlalchemy_url(value):
        return value
    return _sqlite_aiosqlite_url_from_path(value)


class Settings(BaseSettings):
    DB_PATH: str = DEFAULT_DB_PATH
    
    BOT_TOKEN: str
    COVERAGE_WARN_DAYS: int = 7  # Default to 7 days warning
    TZ: str = "Europe/Moscow"
    MORNING_TIME: Optional[str] = None
    EVENING_TIME: Optional[str] = None
    SCHEDULE_ICAL_URL: Optional[str] = None
    # If True, chats with "unset" iCal setting will use SCHEDULE_ICAL_URL as a fallback.
    # If False, the env iCal URL will never be used implicitly.
    SCHEDULE_ICAL_FALLBACK_ENABLED: bool = True
    # 0 = allowed to sync every run; set >0 to throttle (seconds)
    ICAL_SYNC_MIN_INTERVAL_SECONDS: int = 0
    ICAL_SYNC_DAYS: int = 14
    SETUP_TOKEN_TTL_MINUTES: int = 20
    TELEGRAM_PROXY: Optional[str] = None

    @field_validator("MORNING_TIME", "EVENING_TIME")
    @classmethod
    def validate_hhmm(cls, value: Optional[str], info):
        if value is None or value == "":
            return None
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError(f"{info.field_name} must be HH:MM") from exc
        return value

    @field_validator("TZ")
    @classmethod
    def validate_timezone(cls, value: str):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"TZ must be a valid IANA timezone, got '{value}'") from exc
        return value

    @field_validator("DB_PATH", mode="before")
    @classmethod
    def normalize_db_path_value(cls, value):
        if value is None:
            return DEFAULT_DB_PATH
        return normalize_db_path(str(value))
    
    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

settings = Settings()
