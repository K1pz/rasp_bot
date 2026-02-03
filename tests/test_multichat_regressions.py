from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings as env_settings
from app.db.models import SendLog, Settings
from app.db.repos.settings_repo import resolve_ical_url
from app.services import scheduler_service


def test_resolve_ical_url_three_state_logic(monkeypatch):
    monkeypatch.setattr(env_settings, "SCHEDULE_ICAL_URL", "https://example.com/global.ics", raising=False)
    monkeypatch.setattr(env_settings, "SCHEDULE_ICAL_FALLBACK_ENABLED", True, raising=False)

    db_disabled = Settings(
        chat_id=1,
        mode=0,
        morning_time="07:00",
        evening_time=None,
        timezone="UTC",
        ical_url=None,
        ical_enabled=False,  # explicitly disabled for this chat
        updated_at="2025-01-01T00:00:00",
    )

    assert resolve_ical_url(db_disabled) is None

    db_unset = Settings(
        chat_id=2,
        mode=0,
        morning_time="07:00",
        evening_time=None,
        timezone="UTC",
        ical_url=None,  # unset for this chat -> may use env fallback
        ical_enabled=True,
        updated_at="2025-01-01T00:00:00",
    )
    assert resolve_ical_url(db_unset) == "https://example.com/global.ics"
    assert resolve_ical_url(None) == "https://example.com/global.ics"

    monkeypatch.setattr(env_settings, "SCHEDULE_ICAL_FALLBACK_ENABLED", False, raising=False)
    assert resolve_ical_url(db_unset) is None
    assert resolve_ical_url(None) is None


@pytest.mark.asyncio
async def test_scheduler_updates_last_sent_only_on_success(monkeypatch, engine):
    test_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(scheduler_service, "async_session_maker", test_session_maker)

    async with test_session_maker() as session:
        session.add(
            Settings(
                chat_id=777777,
                mode=2,
                morning_time="08:00",
                evening_time="18:00",
                timezone="UTC",
                ical_url=None,  # ensure scheduler won't try iCal sync
                ical_enabled=False,
                updated_at="2025-01-01T00:00:00",
            )
        )
        await session.commit()

    fixed_now = datetime(2025, 1, 2, 19, 0, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(scheduler_service, "get_local_now", lambda tz: fixed_now)
    monkeypatch.setattr(scheduler_service, "get_today", lambda tz: date(2025, 1, 2))
    monkeypatch.setattr(scheduler_service, "get_tomorrow", lambda tz: date(2025, 1, 3))

    async def fake_send_schedule(chat_id: int, target_date: date, kind: str, notify_admin_on_data_gaps: bool = True) -> bool:
        async with test_session_maker() as session:
            if kind == "morning":
                session.add(
                    SendLog(
                        chat_id=chat_id,
                        target_date=target_date.isoformat(),
                        kind=kind,
                        reserved_at="2025-01-02T19:00:00",
                        sent_at="2025-01-02T19:00:01",
                        status="ok",
                        error=None,
                    )
                )
            else:
                session.add(
                    SendLog(
                        chat_id=chat_id,
                        target_date=target_date.isoformat(),
                        kind=kind,
                        reserved_at="2025-01-02T19:00:00",
                        sent_at=None,
                        status="error",
                        error="boom",
                    )
                )
            await session.commit()
        return True

    monkeypatch.setattr(scheduler_service, "send_schedule", fake_send_schedule)

    await scheduler_service._run_periodic_sender()

    async with test_session_maker() as session:
        settings = await session.get(Settings, 777777)
        assert settings is not None
        assert settings.last_sent_morning_date == "2025-01-02"
        assert settings.last_sent_evening_date is None
