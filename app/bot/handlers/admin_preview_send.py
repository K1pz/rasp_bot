from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re

from app.bot.handlers.admin_menu import BTN_PREVIEW, BTN_TEST
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id
from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.settings_repo import SettingsRepo
from app.db.repos.sendlog_repo import SendLogRepo, is_send_success
from app.services.message_builder import build_day_message
from app.services.sender import send_schedule
router = Router()


def _is_chat_write_error(error_text: str | None) -> bool:
    if not error_text:
        return False
    lowered = error_text.lower()
    return any(
        marker in lowered
        for marker in (
            "forbidden:",
            "chat_write_forbidden",
            "not enough rights",
            "bot was kicked",
            "bot is not a member",
            "chat not found",
            "can't send messages",
            "cannot send messages",
        )
    )


@router.message(Command("preview"), F.chat.type == "private")
async def admin_preview(message: Message, state: FSMContext) -> None:

    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    await _send_preview_to_admin(message, date_arg=extract_command_arg(message.text), chat_id=chat_id)


@router.message(Command("send"), F.chat.type == "private")
@router.message(Command("test"), F.chat.type == "private")
async def admin_send_for_date(message: Message, state: FSMContext) -> None:

    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    await _send_to_group(message, date_arg=extract_command_arg(message.text), chat_id=chat_id)


@router.message(F.text == BTN_PREVIEW, F.chat.type == "private")
async def admin_preview_today(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    await _send_preview_to_admin(message, date_arg=None, chat_id=chat_id)


@router.message(F.text == BTN_TEST, F.chat.type == "private")
async def admin_test_send_today(message: Message, state: FSMContext) -> None:

    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    # Button text contains a space (BTN_TEST), so don't treat it as a /send argument.
    await _send_to_group(message, date_arg=None, chat_id=chat_id)


async def _send_preview_to_admin(message: Message, date_arg: str | None, chat_id: int) -> None:
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        schedule_repo = ScheduleRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)
        tz_name = db_settings.timezone or env_settings.TZ
        tz = ZoneInfo(tz_name)
        target_date = parse_target_date(date_arg, tz)
        if not target_date:
            await message.answer(
                "\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u0430\u044f \u0434\u0430\u0442\u0430. "
                "\u041f\u0440\u0438\u043c\u0435\u0440: /preview 2025-02-01 \u0438\u043b\u0438 /preview 01.02.2025"
            )
            return

        items = await schedule_repo.get_by_date(chat_id, target_date.strftime("%Y-%m-%d"))

    preview = build_day_message(target_date, items, tz_name)
    await message.answer(preview)


async def _send_to_group(message: Message, date_arg: str | None, chat_id: int) -> None:
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)
        tz_name = db_settings.timezone or env_settings.TZ

    tz = ZoneInfo(tz_name)
    target_date = parse_target_date(date_arg, tz)
    if not target_date:
        await message.answer(
            "\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u0430\u044f \u0434\u0430\u0442\u0430. "
            "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 /send YYYY-MM-DD, /send DD.MM.YYYY "
            "\u0438\u043b\u0438 /send DD (\u0434\u0435\u043d\u044c \u043c\u0435\u0441\u044f\u0446\u0430)."
        )
        return

    kind = "manual"
    sent_ok = await send_schedule(
        chat_id=chat_id,
        target_date=target_date,
        kind=kind,
        notify_admin_on_data_gaps=False,
    )

    async with async_session_maker() as session:
        sendlog_repo = SendLogRepo(session)
        log = await sendlog_repo.get_log(chat_id, target_date.strftime("%Y-%m-%d"), kind)

    if log and log.status == "error":
        if _is_chat_write_error(log.error):
            await message.answer(
                "\u041d\u0435 \u043c\u043e\u0433\u0443 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0432 \u044d\u0442\u043e\u0442 \u0447\u0430\u0442. "
                "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435, \u0447\u0442\u043e \u0431\u043e\u0442 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d \u0432 \u0447\u0430\u0442 \u0438 \u0443 \u043d\u0435\u0433\u043e \u0435\u0441\u0442\u044c \u043f\u0440\u0430\u0432\u043e \u043f\u0438\u0441\u0430\u0442\u044c."
            )
        else:
            fallback_error = "\u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e"
            await message.answer(
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0432 \u0447\u0430\u0442. "
                f"\u041e\u0448\u0438\u0431\u043a\u0430: {log.error or fallback_error}."
            )
        return

    if log and is_send_success(log.status):
        await message.answer(
            f"\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u043b \u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 {target_date:%Y-%m-%d} \u0432 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u0447\u0430\u0442."
        )
        return

    if log and log.status == "reserved":
        await message.answer(
            "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u0443\u0436\u0435 \u0432 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0435 (\u0437\u0430\u0434\u0430\u0447\u0430 \u0437\u0430\u0440\u0435\u0437\u0435\u0440\u0432\u0438\u0440\u043e\u0432\u0430\u043d\u0430). \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0447\u0443\u0442\u044c \u043f\u043e\u0437\u0436\u0435."
        )
        return

    if sent_ok is False:
        await message.answer(
            "\u041e\u0442\u043f\u0440\u0430\u0432\u043a\u0430 \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u0430 (\u0447\u0430\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0438\u043b\u0438 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0443\u0436\u0435 \u0431\u044b\u043b\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e)."
        )
        return

    await message.answer(
        "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0438. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 send_log."
    )


def extract_command_arg(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


def parse_target_date(arg: str | None, tz: ZoneInfo) -> date | None:
    now = datetime.now(tz=tz).date()
    if not arg:
        return now
    val = arg.strip()

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue

    if re.match(r"^\d{1,2}$", val):
        day = int(val)
        try:
            return date(now.year, now.month, day)
        except ValueError:
            return None

    return None
