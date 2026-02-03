from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import group_setup


class DummySession:
    pass


class DummySessionContext:
    async def __aenter__(self):
        return DummySession()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_group_status_uses_settings_fields(monkeypatch):
    group_id = -2004

    settings = SimpleNamespace(
        mode=2,
        morning_time="07:30",
        evening_time="19:00",
        timezone="Europe/Moscow",
        last_ical_sync_at="2024-01-02T03:04:05",
        coverage_end_date="2024-01-20",
    )

    class DummySettingsRepo:
        def __init__(self, session):
            self.get_settings = AsyncMock(return_value=settings)

    message = SimpleNamespace(
        chat=SimpleNamespace(id=group_id),
        answer=AsyncMock(),
    )

    monkeypatch.setattr(group_setup, "async_session_maker", lambda: DummySessionContext())
    monkeypatch.setattr(group_setup, "SettingsRepo", DummySettingsRepo)

    await group_setup.group_status(message)

    message.answer.assert_awaited_once()
    response_text = message.answer.call_args.args[0]
    assert "Последняя синхронизация iCal: 2024-01-02 03:04" in response_text
    assert "Покрытие расписания до: 2024-01-20" in response_text
    assert "последняя загрузка" not in response_text.lower()
    assert ".." not in response_text
