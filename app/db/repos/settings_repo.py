from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.db.models import Settings
from app.config import settings as env_settings
from datetime import datetime

def _normalize_env_ical_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    return url or None

def get_ical_setting_state(db_settings: Settings | None) -> str:
    """
    Returns one of:
    - "missing": no per-chat settings row exists
    - "disabled": chat explicitly disabled iCal
    - "explicit": chat stored a concrete URL
    - "unset": chat has no stored URL (may use env fallback)
    """
    if db_settings is None:
        return "missing"

    # Be defensive: older code/tests might construct Settings without ical_enabled.
    if getattr(db_settings, "ical_enabled", True) is False:
        return "disabled"

    raw = (db_settings.ical_url or "").strip()
    # Legacy compatibility: older DBs used "-" as a "disabled" marker.
    if raw == "-":
        return "disabled"
    if raw:
        return "explicit"
    return "unset"

def resolve_ical_url(db_settings: Settings | None) -> str | None:
    """
    Resolve the effective iCal URL for a chat.

    3 states (per chat):
    - Explicit URL: use it.
    - Unset (iCal enabled, ical_url NULL/empty): may fall back to env default (if SCHEDULE_ICAL_FALLBACK_ENABLED).
    - Disabled (iCal enabled flag is false): never use iCal, even if env default exists.
    """
    env_default = _normalize_env_ical_url(env_settings.SCHEDULE_ICAL_URL)
    fallback_enabled = bool(getattr(env_settings, "SCHEDULE_ICAL_FALLBACK_ENABLED", True))

    if db_settings is None:
        return env_default if fallback_enabled else None

    if getattr(db_settings, "ical_enabled", True) is False:
        return None

    raw = (db_settings.ical_url or "").strip()
    # Legacy compatibility: older DBs used "-" as a "disabled" marker.
    if raw == "-":
        return None
    if raw:
        return raw

    # Unset for this chat → optionally fall back to env.
    return env_default if fallback_enabled else None

class SettingsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_default_settings(self, chat_id: int) -> dict:
        now = datetime.now().isoformat()
        return {
            "chat_id": chat_id,
            "mode": 0,
            "morning_time": env_settings.MORNING_TIME or "07:00",
            "evening_time": env_settings.EVENING_TIME,
            "timezone": env_settings.TZ,
            # IMPORTANT: keep iCal unset by default to preserve the 3-state logic:
            # - explicit URL (stored), unset (iCal enabled + NULL → optional env fallback), disabled (iCal enabled flag false).
            "ical_url": None,
            "ical_enabled": True,
            "updated_at": now,
        }

    async def get_settings(self, chat_id: int) -> Settings | None:
        defaults = self._build_default_settings(chat_id)
        insert_stmt = sqlite_insert(Settings).values(**defaults).on_conflict_do_nothing(
            index_elements=["chat_id"]
        )
        result = await self.session.execute(insert_stmt)
        if result.rowcount == 1:
            await self.session.commit()

        stmt = select(Settings).where(Settings.chat_id == chat_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all_settings(self) -> list[Settings]:
        stmt = select(Settings).where(Settings.chat_id.is_not(None))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_settings(self, chat_id: int, **kwargs):
        # Ensure updated_at is always set
        if 'updated_at' not in kwargs:
            kwargs['updated_at'] = datetime.now().isoformat()
            
        defaults = self._build_default_settings(chat_id)
        values = {**defaults, **kwargs}
        stmt = sqlite_insert(Settings).values(**values).on_conflict_do_update(
            index_elements=["chat_id"],
            set_=kwargs,
        )
        await self.session.execute(stmt)
            
    async def ensure_settings(self, chat_id: int) -> Settings:
        return await self.get_settings(chat_id)
