import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from zoneinfo import ZoneInfo

from app.bot.handlers.admin_menu import BTN_SETTINGS
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id
from app.bot.states.admin import SettingsStates
from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url, get_ical_setting_state
from app.ical.fetcher import fetch_ical, IcalFetchError
from app.ical.parser import parse_ical
from app.services.date_service import parse_hhmm
from app.services.scheduler_service import apply_schedule

router = Router()

BOT_TIMEZONE = "Europe/Moscow"


def _ask_mode_text() -> str:
    return (
        "Выберите режим работы:\n"
        "0 — не отправлять автоматически\n"
        "1 — один раз в день (утром)\n"
        "2 — два раза в день (утром и вечером)"
    )


@router.message(Command("settings"), F.chat.type == "private")
@router.message(F.text == BTN_SETTINGS, F.chat.type == "private")
async def admin_settings(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    async with async_session_maker() as session:
        repo = SettingsRepo(session)
        db_settings = await repo.get_settings(chat_id)
        existing_ical_url = db_settings.ical_url
        existing_ical_enabled = getattr(db_settings, "ical_enabled", True)

    await state.clear()
    await state.update_data(
        active_chat_id=chat_id,
        existing_ical_url=existing_ical_url,
        existing_ical_enabled=existing_ical_enabled,
    )
    await state.set_state(SettingsStates.mode)
    await message.answer(_ask_mode_text())


@router.message(SettingsStates.mode, F.chat.type == "private")
async def settings_set_mode(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    try:
        mode = int((message.text or "").strip())
    except ValueError:
        await message.answer("Введите 0, 1 или 2.")
        return

    if mode not in (0, 1, 2):
        await message.answer("Введите 0, 1 или 2.")
        return

    await state.update_data(mode=mode)
    await state.set_state(SettingsStates.morning_time)
    await message.answer("Введите время утренней рассылки (HH:MM), например 07:00:")


@router.message(SettingsStates.morning_time, F.chat.type == "private")
async def settings_set_morning(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    value = (message.text or "").strip()
    try:
        parse_hhmm(value)
    except Exception:
        await message.answer("Неверный формат. Используйте HH:MM, например 07:00.")
        return

    await state.update_data(morning_time=value)
    data = await state.get_data()
    if data.get("mode") == 2:
        await state.set_state(SettingsStates.evening_time)
        await message.answer("Введите время вечерней рассылки (HH:MM), например 19:00:")
    else:
        await state.update_data(evening_time=None)
        await state.update_data(timezone=BOT_TIMEZONE)
        await state.set_state(SettingsStates.ical_url)
        await message.answer(
            "Отправьте ссылку iCal/ICS.\n"
            "Команды:\n"
            "- '-' — отключить iCal для этого чата (не использовать даже дефолт из .env)\n"
            "- 'default' — использовать дефолт из .env (если включено)\n"
            "- 'skip' — оставить текущую настройку"
        )


@router.message(SettingsStates.evening_time, F.chat.type == "private")
async def settings_set_evening(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    value = (message.text or "").strip()
    try:
        parse_hhmm(value)
    except Exception:
        await message.answer("Неверный формат. Используйте HH:MM, например 19:00.")
        return

    await state.update_data(evening_time=value)
    await state.set_state(SettingsStates.ical_url)
    await message.answer(
        "Отправьте ссылку iCal/ICS.\n"
        "Команды:\n"
        "- '-' — отключить iCal для этого чата (не использовать даже дефолт из .env)\n"
        "- 'default' — использовать дефолт из .env (если включено)\n"
        "- 'skip' — оставить текущую настройку"
    )


@router.message(SettingsStates.timezone, F.chat.type == "private")
async def settings_timezone_legacy(message: Message, state: FSMContext) -> None:
    """
    Legacy handler: older versions asked the user for timezone during /settings.
    Timezone is fixed now, but we keep this to avoid users getting stuck mid-flow.
    """
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    await state.update_data(timezone=BOT_TIMEZONE)
    await state.set_state(SettingsStates.ical_url)
    await message.answer(
        "Часовой пояс фиксированный: Europe/Moscow.\n"
        "Отправьте ссылку iCal/ICS.\n"
        "Команды:\n"
        "- '-' — отключить iCal для этого чата (не использовать даже дефолт из .env)\n"
        "- 'default' — использовать дефолт из .env (если включено)\n"
        "- 'skip' — оставить текущую настройку"
    )


@router.message(SettingsStates.ical_url, F.chat.type == "private")
async def settings_set_ical(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    value = (message.text or "").strip()
    data = await state.get_data()
    existing_ical = data.get("existing_ical_url")
    existing_ical_enabled = data.get("existing_ical_enabled", True)

    value_lc = value.lower()
    if value_lc in ("skip", "пропустить"):
        ical_url = existing_ical
        ical_enabled = existing_ical_enabled
    elif value in ("-", "?"):
        # Explicitly disabled for this chat (do not use env fallback either).
        ical_url = None
        ical_enabled = False
    elif value_lc in ("default", "env", "по умолчанию"):
        # Unset: may fall back to env default (if enabled).
        ical_url = None
        ical_enabled = True
    else:
        ical_url = value or None
        ical_enabled = True

    if ical_enabled and ical_url and (ical_url != existing_ical or existing_ical_enabled is False):
        tz_name = BOT_TIMEZONE
        try:
            ics_text = await asyncio.to_thread(fetch_ical, ical_url)
            tzinfo = ZoneInfo(tz_name)
            today = datetime.now(tzinfo).date()
            window_days = max(1, int(env_settings.ICAL_SYNC_DAYS or 14))
            window_start = today
            window_end = today + timedelta(days=window_days - 1)
            parsed = await asyncio.to_thread(parse_ical, ics_text, tz_name, window_start, window_end)
        except IcalFetchError as exc:
            await message.answer(
                f"Не удалось загрузить iCal: {exc}. Проверьте ссылку и попробуйте снова."
            )
            return
        except Exception:
            await message.answer(
                "Не удалось разобрать iCal. Проверьте, что ссылка ведет на .ics, и попробуйте снова."
            )
            return

        if parsed.warnings and not parsed.items:
            await message.answer(
                "iCal не содержит событий или содержит ошибки. Проверьте ссылку и попробуйте снова."
            )
            return

    await state.clear()
    await state.update_data(active_chat_id=chat_id)

    async with async_session_maker() as session:
        repo = SettingsRepo(session)
        await repo.upsert_settings(
            chat_id=chat_id,
            mode=data.get("mode", 0),
            morning_time=data.get("morning_time", "07:00"),
            evening_time=data.get("evening_time"),
            timezone=BOT_TIMEZONE,
            ical_url=ical_url,
            ical_enabled=ical_enabled,
        )
        await session.commit()
        db_settings = await repo.get_settings(chat_id)

    apply_schedule(db_settings)

    effective_ical = resolve_ical_url(db_settings)
    ical_state = get_ical_setting_state(db_settings)
    if ical_state == "disabled":
        ical_status = "отключён"
    elif ical_state == "unset" and effective_ical:
        ical_status = "по умолчанию (.env)"
    else:
        ical_status = "задан" if effective_ical else "не задан"
    await message.answer(
        "Настройки сохранены:\n"
        f"Режим: {db_settings.mode}\n"
        f"Утро: {db_settings.morning_time}\n"
        f"Вечер: {db_settings.evening_time or '-'}\n"
        f"Часовой пояс: {BOT_TIMEZONE} (фиксированный)\n"
        f"iCal: {ical_status}"
    )
