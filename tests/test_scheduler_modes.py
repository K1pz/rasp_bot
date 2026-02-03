from datetime import date, datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest

from app.db.models import Settings
from app.services import catchup_service
from app.services.scheduler_service import apply_schedule, init_scheduler, scheduler


def _make_settings(
    mode: int,
    *,
    chat_id: int = 123,
    morning_time: str = "08:00",
    evening_time: str | None = "18:00",
    timezone: str = "UTC",
) -> Settings:
    return Settings(
        chat_id=chat_id,
        mode=mode,
        morning_time=morning_time,
        evening_time=evening_time,
        timezone=timezone,
        updated_at="2025-01-01T00:00:00",
    )


def _reset_scheduler() -> None:
    scheduler.remove_all_jobs()
    init_scheduler("UTC")


def test_apply_schedule_registers_periodic_sender_job():
    _reset_scheduler()
    settings = _make_settings(0)

    apply_schedule(settings)

    assert scheduler.get_job("periodic_sender") is not None


@pytest.mark.asyncio
async def test_run_catchup_mode_0_does_not_send(monkeypatch):
    settings = _make_settings(0)

    send_mock = AsyncMock(return_value=True)
    alert_mock = AsyncMock()

    monkeypatch.setattr(catchup_service, "send_schedule", send_mock)
    monkeypatch.setattr(catchup_service, "alert_admin", alert_mock)

    await catchup_service.run_catchup(settings)

    send_mock.assert_not_awaited()
    alert_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_catchup_mode_1_only_morning(monkeypatch):
    settings = _make_settings(1, morning_time="08:00", evening_time="18:00")

    fixed_now = datetime(2025, 1, 2, 9, 0, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(catchup_service, "get_local_now", lambda tz: fixed_now)
    monkeypatch.setattr(catchup_service, "get_today", lambda tz: date(2025, 1, 2))
    monkeypatch.setattr(catchup_service, "get_tomorrow", lambda tz: date(2025, 1, 3))

    send_mock = AsyncMock(return_value=True)
    alert_mock = AsyncMock()

    monkeypatch.setattr(catchup_service, "send_schedule", send_mock)
    monkeypatch.setattr(catchup_service, "alert_admin", alert_mock)

    class DummySessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class DummySendLogRepo:
        def __init__(self, session):
            self.session = session

        async def find_stuck_reserved(self, older_than_minutes: int):
            return []

    monkeypatch.setattr(catchup_service, "async_session_maker", lambda: DummySessionContext())
    monkeypatch.setattr(catchup_service, "SendLogRepo", DummySendLogRepo)

    await catchup_service.run_catchup(settings)

    assert send_mock.await_count == 1
    _, kwargs = send_mock.await_args
    assert kwargs["kind"] == "morning"
    assert kwargs["target_date"] == date(2025, 1, 2)


@pytest.mark.asyncio
async def test_run_catchup_mode_2_morning_and_evening(monkeypatch):
    settings = _make_settings(2, morning_time="08:00", evening_time="18:00")

    fixed_now = datetime(2025, 1, 2, 19, 0, tzinfo=ZoneInfo("UTC"))
    monkeypatch.setattr(catchup_service, "get_local_now", lambda tz: fixed_now)
    monkeypatch.setattr(catchup_service, "get_today", lambda tz: date(2025, 1, 2))
    monkeypatch.setattr(catchup_service, "get_tomorrow", lambda tz: date(2025, 1, 3))

    send_mock = AsyncMock(return_value=True)
    alert_mock = AsyncMock()

    monkeypatch.setattr(catchup_service, "send_schedule", send_mock)
    monkeypatch.setattr(catchup_service, "alert_admin", alert_mock)

    class DummySessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class DummySendLogRepo:
        def __init__(self, session):
            self.session = session

        async def find_stuck_reserved(self, older_than_minutes: int):
            return []

    monkeypatch.setattr(catchup_service, "async_session_maker", lambda: DummySessionContext())
    monkeypatch.setattr(catchup_service, "SendLogRepo", DummySendLogRepo)

    await catchup_service.run_catchup(settings)

    assert send_mock.await_count == 2
    calls = [call.kwargs for call in send_mock.await_args_list]
    assert {"kind": "morning", "target_date": date(2025, 1, 2), "chat_id": 123} in calls
    assert {"kind": "evening", "target_date": date(2025, 1, 3), "chat_id": 123} in calls
