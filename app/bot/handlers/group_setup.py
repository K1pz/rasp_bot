import logging
from datetime import datetime, date

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url
from app.db.repos.setup_tokens_repo import SetupTokenRepo
from app.services.date_service import get_next_week_window, get_today, get_tomorrow, get_week_window
from app.services.ical_sync_service import sync_ical_schedule
from app.services.message_builder import build_day_message, build_range_message, build_week_range_message, split_telegram, ParseMode
from app.services.scheduler_service import apply_schedule

router = Router()


@router.message(CommandStart(), F.chat.type.in_({"group", "supergroup"}))
async def start_group(message: Message) -> None:
    await message.answer(
        "Привет! Для настройки отправьте /setup в этом чате."
    )


@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def on_bot_added(event: ChatMemberUpdated) -> None:
    try:
        old_status = getattr(event.old_chat_member, "status", None)
        new_status = getattr(event.new_chat_member, "status", None)
        if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
            await event.bot.send_message(
                event.chat.id,
                "Привет! Для настройки отправьте команду /setup.\n"
                "Если бот не видит обычные сообщения — используйте команды или упоминание бота (privacy mode).",
            )
    except Exception:
        logging.exception("Failed to handle my_chat_member update.")


async def _build_settings_keyboard(message: Message, setup_token: str) -> InlineKeyboardMarkup | None:
    try:
        me = await message.bot.get_me()
        if not me.username:
            return None
        link = f"https://t.me/{me.username}?start=setup_{setup_token}"
    except Exception:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть настройки в личке", url=link)]]
    )


async def _try_send_private_settings(message: Message, setup_token: str) -> bool:
    user = message.from_user
    if not user:
        return False

    keyboard = await _build_settings_keyboard(message, setup_token)
    if keyboard:
        text = "Откройте настройки в личке по кнопке."
    else:
        text = (
            "Откройте диалог с ботом и отправьте команду "
            f"/start setup_{setup_token}."
        )

    try:
        await message.bot.send_message(user.id, text, reply_markup=keyboard)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    except Exception:
        logging.exception("Failed to send private settings link.")
        return False


@router.message(Command("setup", "bind"), F.chat.type.in_({"group", "supergroup"}))
async def setup_group(message: Message) -> None:
    logging.info(
        "Received /setup from user %s in chat %s",
        getattr(message.from_user, "id", None),
        message.chat.id,
    )

    async with async_session_maker() as session:
        repo = SettingsRepo(session)
        token_repo = SetupTokenRepo(session)
        db_settings = await repo.ensure_settings(message.chat.id)
        setup_token = await token_repo.create_token(
            message.chat.id,
            getattr(message.from_user, "id", None),
            env_settings.SETUP_TOKEN_TTL_MINUTES,
        )
        await session.commit()
    apply_schedule(db_settings)

    keyboard = await _build_settings_keyboard(message, setup_token)
    dm_sent = await _try_send_private_settings(message, setup_token)

    if dm_sent:
        await message.answer(
            "Ссылка настроек отправлена в личные сообщения.",
            reply_markup=keyboard,
        )
        return

    if keyboard:
        await message.answer(
            "Не могу написать вам в личку. Откройте диалог с ботом, нажмите Start, "
            "затем возвращайтесь сюда и нажмите кнопку.",
            reply_markup=keyboard,
        )
        return

    await message.answer(
        "Не могу написать вам в личку. Откройте диалог с ботом, нажмите Start, "
        f"затем отправьте /start setup_{setup_token}."
    )


@router.message(Command("settings"), F.chat.type.in_({"group", "supergroup"}))
async def settings_link(message: Message) -> None:
    async with async_session_maker() as session:
        repo = SettingsRepo(session)
        token_repo = SetupTokenRepo(session)
        await repo.ensure_settings(message.chat.id)
        setup_token = await token_repo.create_token(
            message.chat.id,
            getattr(message.from_user, "id", None),
            env_settings.SETUP_TOKEN_TTL_MINUTES,
        )
        await session.commit()
    keyboard = await _build_settings_keyboard(message, setup_token)
    dm_sent = await _try_send_private_settings(message, setup_token)

    if dm_sent:
        await message.answer(
            "Ссылка настроек отправлена в личные сообщения.",
            reply_markup=keyboard,
        )
        return

    if keyboard:
        await message.answer(
            "Не могу написать вам в личку. Откройте диалог с ботом, нажмите Start, "
            "затем возвращайтесь сюда и нажмите кнопку.",
            reply_markup=keyboard,
        )
        return

    await message.answer(
        "Не могу написать вам в личку. Откройте диалог с ботом, нажмите Start, "
        f"затем отправьте /start setup_{setup_token}."
    )


def _format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        ts = datetime.fromisoformat(raw)
    except Exception:
        return value
    if ts.time() == datetime.min.time():
        return ts.strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d %H:%M")


@router.message(Command("status"), F.chat.type.in_({"group", "supergroup"}))
async def group_status(message: Message) -> None:
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(message.chat.id)
        mode = db_settings.mode
        morning_time = db_settings.morning_time
        evening_time = db_settings.evening_time
        timezone = db_settings.timezone
        last_ical_sync_at = db_settings.last_ical_sync_at
        coverage_end_date = db_settings.coverage_end_date

    response = (
        "Статус настроек\n"
        f"Режим: {mode}\n"
        f"Утро: {morning_time or '—'}\n"
        f"Вечер: {evening_time or '—'}\n"
        f"Часовой пояс: {timezone or '—'}\n"
        f"Последняя синхронизация iCal: {_format_datetime(last_ical_sync_at)}\n"
        f"Покрытие расписания до: {_format_datetime(coverage_end_date)}"
    )

    await message.answer(response)


async def _resolve_chat_context(chat_id: int) -> tuple[str, str | None]:
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)
        tz = (db_settings.timezone if db_settings else None) or env_settings.TZ
        ical_url = resolve_ical_url(db_settings) if db_settings else None
    return tz, ical_url


async def _send_range_schedule(
    message: Message,
    date_from: date,
    date_to: date,
    tz: str,
    ical_url: str | None,
    *,
    week_style: bool = False,
) -> None:
    chat_id = message.chat.id

    if ical_url:
        try:
            await sync_ical_schedule(chat_id)
        except Exception:
            logging.exception("iCal sync failed for chat_id=%s", chat_id)

    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()

    async with async_session_maker() as session:
        schedule_repo = ScheduleRepo(session)
        items = await schedule_repo.get_by_date_range(chat_id, date_from_str, date_to_str)

    if week_style:
        message_text = build_week_range_message(date_from, date_to, items, tz)
    else:
        message_text = build_range_message(date_from, date_to, items, tz)
    for chunk in split_telegram(message_text):
        await message.answer(chunk, parse_mode=ParseMode.HTML)


@router.message(Command("today"), F.chat.type.in_({"group", "supergroup"}))
async def group_today(message: Message) -> None:
    tz, ical_url = await _resolve_chat_context(message.chat.id)
    target_date = get_today(tz)
    await _send_range_schedule(message, target_date, target_date, tz, ical_url)


@router.message(Command("tomorrow"), F.chat.type.in_({"group", "supergroup"}))
async def group_tomorrow(message: Message) -> None:
    tz, ical_url = await _resolve_chat_context(message.chat.id)
    target_date = get_tomorrow(tz)
    await _send_range_schedule(message, target_date, target_date, tz, ical_url)


@router.message(Command("week"), F.chat.type.in_({"group", "supergroup"}))
async def group_week(message: Message) -> None:
    tz, ical_url = await _resolve_chat_context(message.chat.id)
    date_from, date_to = get_week_window(tz)
    await _send_range_schedule(message, date_from, date_to, tz, ical_url, week_style=True)


@router.message(Command("nextweek"), F.chat.type.in_({"group", "supergroup"}))
async def group_next_week(message: Message) -> None:
    tz, ical_url = await _resolve_chat_context(message.chat.id)
    date_from, date_to = get_next_week_window(tz)
    await _send_range_schedule(message, date_from, date_to, tz, ical_url, week_style=True)
