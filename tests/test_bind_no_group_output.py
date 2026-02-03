from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import group_setup


class DummySession:
    def __init__(self):
        self.commit = AsyncMock()


class DummySessionContext:
    async def __aenter__(self):
        return DummySession()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySettingsRepo:
    last_instance = None

    def __init__(self, session):
        self.ensure_settings = AsyncMock(return_value=SimpleNamespace())
        DummySettingsRepo.last_instance = self


class DummySetupTokenRepo:
    last_instance = None

    def __init__(self, session):
        self.create_token = AsyncMock(return_value="token123")
        DummySetupTokenRepo.last_instance = self


@pytest.mark.asyncio
async def test_setup_answers_in_group(monkeypatch):
    group_id = -2002
    bot = SimpleNamespace(send_message=AsyncMock())

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1001),
        chat=SimpleNamespace(id=group_id, title="Test Group"),
        bot=bot,
        answer=AsyncMock(),
    )

    monkeypatch.setattr(group_setup, "async_session_maker", lambda: DummySessionContext())
    monkeypatch.setattr(group_setup, "SettingsRepo", DummySettingsRepo)
    monkeypatch.setattr(group_setup, "SetupTokenRepo", DummySetupTokenRepo)
    monkeypatch.setattr(group_setup, "apply_schedule", lambda _settings: None)
    monkeypatch.setattr(group_setup, "_build_settings_keyboard", AsyncMock(return_value=None))
    monkeypatch.setattr(group_setup, "_try_send_private_settings", AsyncMock(return_value=True))

    await group_setup.setup_group(message)

    message.answer.assert_awaited_once()
    response_text = message.answer.call_args.args[0]
    assert "Ссылка настроек отправлена" in response_text
    DummySettingsRepo.last_instance.ensure_settings.assert_awaited_once_with(group_id)


@pytest.mark.asyncio
async def test_setup_group_fallback_text(monkeypatch):
    group_id = -2003
    bot = SimpleNamespace(send_message=AsyncMock())

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1002),
        chat=SimpleNamespace(id=group_id, title="Test Group"),
        bot=bot,
        answer=AsyncMock(),
    )

    monkeypatch.setattr(group_setup, "async_session_maker", lambda: DummySessionContext())
    monkeypatch.setattr(group_setup, "SettingsRepo", DummySettingsRepo)
    monkeypatch.setattr(group_setup, "SetupTokenRepo", DummySetupTokenRepo)
    monkeypatch.setattr(group_setup, "apply_schedule", lambda _settings: None)
    monkeypatch.setattr(group_setup, "_build_settings_keyboard", AsyncMock(return_value=None))
    monkeypatch.setattr(group_setup, "_try_send_private_settings", AsyncMock(return_value=False))

    await group_setup.setup_group(message)

    message.answer.assert_awaited_once()
    response_text = message.answer.call_args.args[0]
    assert "Не могу написать вам в личку" in response_text
    assert "/start setup_token123" in response_text


@pytest.mark.asyncio
async def test_settings_keyboard_text(monkeypatch):
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="bot")))
    message = SimpleNamespace(bot=bot)

    keyboard = await group_setup._build_settings_keyboard(message, "token123")

    assert keyboard.inline_keyboard[0][0].text == "Открыть настройки в личке"
