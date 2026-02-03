from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    DB_PATH: str = "sqlite+aiosqlite:///./data/bot.db"
    
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
    
    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"

settings = Settings()
