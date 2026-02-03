import html
import json
import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.chat_access import is_user_chat_admin, is_user_chat_member
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id
from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.repos.settings_repo import SettingsRepo, get_ical_setting_state
from app.db.repos.setup_tokens_repo import SetupTokenRepo
from app.services.date_service import parse_hhmm
from app.services.scheduler_service import apply_schedule

router = Router()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportedChatSettings:
    chat_id: int
    timezone: str
    mode: int
    morning_time: str
    evening_time: str | None
    ical_enabled: bool
    ical_url: str | None


def _json_loads_or_none(payload: str) -> Any | None:
    try:
        return json.loads(payload)
    except Exception:
        return None


def _extract_import_payload(message: Message) -> str | None:
    text = (message.text or "").strip()
    if text:
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1].strip() or None

    reply = getattr(message, "reply_to_message", None)
    reply_text = (getattr(reply, "text", None) or "").strip()
    if reply_text:
        return reply_text

    return None


def _normalize_ical_fields(raw_ical_enabled: Any, raw_ical_url: Any) -> tuple[bool, str | None]:
    ical_enabled = bool(raw_ical_enabled)
    ical_url = None
    if raw_ical_url is not None:
        if isinstance(raw_ical_url, str):
            ical_url = raw_ical_url.strip() or None
        else:
            ical_url = str(raw_ical_url).strip() or None

    if not ical_enabled:
        return False, None

    # Legacy compatibility: older DBs used "-" as a "disabled" marker.
    if (ical_url or "").strip() == "-":
        return False, None

    return True, ical_url


def _parse_imported_settings(data: Any, expected_chat_id: int) -> tuple[ImportedChatSettings | None, str | None]:
    if not isinstance(data, dict):
        return None, "\u041e\u0436\u0438\u0434\u0430\u044e JSON-\u043e\u0431\u044a\u0435\u043a\u0442 (\u0441\u043b\u043e\u0432\u0430\u0440\u044c)."

    raw_chat_id = data.get("chat_id")
    try:
        chat_id = int(raw_chat_id)
    except Exception:
        return None, "\u041f\u043e\u043b\u0435 chat_id \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e \u0438 \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c."

    if chat_id != expected_chat_id:
        return (
            None,
            "\u042d\u0442\u043e\u0442 JSON \u0434\u043b\u044f \u0434\u0440\u0443\u0433\u043e\u0433\u043e \u0447\u0430\u0442\u0430. "
            f"\u0416\u0434\u0443 chat_id={expected_chat_id}, \u043d\u043e \u043f\u0440\u0438\u0448\u043b\u043e chat_id={chat_id}.",
        )

    timezone = (data.get("timezone") or "").strip()
    if not timezone:
        return None, "\u041f\u043e\u043b\u0435 timezone \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e."
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return None, f"\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 timezone: {timezone}"

    try:
        mode = int(data.get("mode"))
    except Exception:
        return None, "\u041f\u043e\u043b\u0435 mode \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e \u0438 \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c 0/1/2."
    if mode not in (0, 1, 2):
        return None, "\u041f\u043e\u043b\u0435 mode \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c 0/1/2."

    morning_time = (data.get("morning_time") or "").strip()
    if not morning_time:
        return None, "\u041f\u043e\u043b\u0435 morning_time \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e."
    try:
        parse_hhmm(morning_time)
    except Exception:
        return None, "\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 morning_time. \u0416\u0434\u0443 HH:MM, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 07:00."

    raw_evening = data.get("evening_time")
    evening_time = None
    if raw_evening is not None:
        evening_time = (str(raw_evening) or "").strip() or None
    if mode != 2:
        evening_time = None
    if mode == 2:
        if not evening_time:
            return None, "\u0414\u043b\u044f mode=2 \u043d\u0443\u0436\u043d\u043e \u0443\u043a\u0430\u0437\u0430\u0442\u044c evening_time."
        try:
            parse_hhmm(evening_time)
        except Exception:
            return None, "\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 evening_time. \u0416\u0434\u0443 HH:MM, \u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440 19:00."

    raw_ical_enabled = data.get("ical_enabled", True)
    raw_ical_url = data.get("ical_url")
    ical_enabled, ical_url = _normalize_ical_fields(raw_ical_enabled, raw_ical_url)

    return (
        ImportedChatSettings(
            chat_id=chat_id,
            timezone=timezone,
            mode=mode,
            morning_time=morning_time,
            evening_time=evening_time,
            ical_enabled=ical_enabled,
            ical_url=ical_url,
        ),
        None,
    )


async def _resolve_target_chat_id(message: Message, state) -> int | None:
    if message.chat.type == "private":
        return await _get_active_chat_id(state, message)
    return message.chat.id


async def _has_transfer_access(message: Message, chat_id: int) -> bool:
    user = message.from_user
    if not user:
        return False

    if not await is_user_chat_member(message.bot, chat_id, user.id):
        return False

    if await is_user_chat_admin(message.bot, chat_id, user.id):
        return True

    async with async_session_maker() as session:
        token_repo = SetupTokenRepo(session)
        return await token_repo.is_chat_setup_token_creator(chat_id=chat_id, user_id=user.id)


def _export_payload_from_db_settings(chat_id: int, db_settings) -> dict[str, Any]:
    ical_state = get_ical_setting_state(db_settings)
    if ical_state == "disabled":
        ical_enabled = False
        ical_url = None
    elif ical_state == "explicit":
        ical_enabled = True
        ical_url = (db_settings.ical_url or "").strip() or None
    else:
        ical_enabled = True
        ical_url = None

    return {
        "chat_id": chat_id,
        "timezone": db_settings.timezone,
        "mode": db_settings.mode,
        "morning_time": db_settings.morning_time,
        "evening_time": db_settings.evening_time,
        "ical_enabled": ical_enabled,
        "ical_url": ical_url,
    }


@router.message(Command("export_settings"))
async def export_settings(message: Message, state) -> None:
    chat_id = await _resolve_target_chat_id(message, state)
    if not chat_id:
        return

    if not await _has_transfer_access(message, chat_id):
        await message.answer(
            "\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430. \u041d\u0443\u0436\u0435\u043d \u0430\u0434\u043c\u0438\u043d \u0447\u0430\u0442\u0430 \u0438\u043b\u0438 \u0430\u0432\u0442\u043e\u0440 setup-\u0442\u043e\u043a\u0435\u043d\u0430."
        )
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)

    payload = _export_payload_from_db_settings(chat_id, db_settings)
    settings_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    warn = (
        "\u26a0\ufe0f \u0412\u043d\u0438\u043c\u0430\u043d\u0438\u0435: iCal URL \u043c\u043e\u0436\u0435\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442\u044c \u0441\u0435\u043a\u0440\u0435\u0442\u043d\u044b\u0439 \u0442\u043e\u043a\u0435\u043d.\n"
        "\u041d\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0443\u0439\u0442\u0435 \u044d\u0442\u043e\u0442 JSON \u0432 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0445 \u043a\u0430\u043d\u0430\u043b\u0430\u0445."
    )
    text = (
        f"\u042d\u043a\u0441\u043f\u043e\u0440\u0442 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043a \u0447\u0430\u0442\u0430 chat_id={chat_id}.\n"
        f"{warn}\n\n<pre>{html.escape(settings_json)}</pre>"
    )

    if message.chat.type == "private":
        await message.answer(text)
        return

    user = message.from_user
    if not user:
        return

    try:
        await message.bot.send_message(user.id, text)
        await message.answer("\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u043b \u0432 \u043b\u0438\u0447\u043a\u0443.")
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer(
            "\u041d\u0435 \u043c\u043e\u0433\u0443 \u043d\u0430\u043f\u0438\u0441\u0430\u0442\u044c \u0432 \u043b\u0438\u0447\u043a\u0443. "
            "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0434\u0438\u0430\u043b\u043e\u0433 \u0441 \u0431\u043e\u0442\u043e\u043c, \u043d\u0430\u0436\u043c\u0438\u0442\u0435 Start \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u0443."
        )
    except Exception:
        logger.exception("Failed to DM exported settings.")
        await message.answer("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0432 \u043b\u0438\u0447\u043a\u0443.")


@router.message(Command("import_settings"))
async def import_settings(message: Message, state) -> None:
    chat_id = await _resolve_target_chat_id(message, state)
    if not chat_id:
        return

    if not await _has_transfer_access(message, chat_id):
        await message.answer(
            "\u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u0430. \u041d\u0443\u0436\u0435\u043d \u0430\u0434\u043c\u0438\u043d \u0447\u0430\u0442\u0430 \u0438\u043b\u0438 \u0430\u0432\u0442\u043e\u0440 setup-\u0442\u043e\u043a\u0435\u043d\u0430."
        )
        return

    payload_text = _extract_import_payload(message)
    if not payload_text:
        await message.answer(
            "\u041f\u0440\u0438\u0448\u043b\u0438\u0442\u0435 JSON \u043f\u043e\u0441\u043b\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b \u0438\u043b\u0438 \u043e\u0442\u0432\u0435\u0442\u043e\u043c \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0441 JSON.\n"
            "\u041f\u0440\u0438\u043c\u0435\u0440: /import_settings {\"chat_id\": 123, ...}"
        )
        return

    data = _json_loads_or_none(payload_text)
    if data is None:
        await message.answer(
            "\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0437\u043e\u0431\u0440\u0430\u0442\u044c JSON. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0444\u043e\u0440\u043c\u0430\u0442."
        )
        return

    imported, error = _parse_imported_settings(data, expected_chat_id=chat_id)
    if error:
        await message.answer(error)
        return

    assert imported is not None

    async with async_session_maker() as session:
        repo = SettingsRepo(session)
        await repo.upsert_settings(
            chat_id=imported.chat_id,
            mode=imported.mode,
            morning_time=imported.morning_time,
            evening_time=imported.evening_time,
            timezone=imported.timezone or env_settings.TZ,
            ical_url=imported.ical_url,
            ical_enabled=imported.ical_enabled,
        )
        await session.commit()
        db_settings = await repo.get_settings(imported.chat_id)

    apply_schedule(db_settings)

    await message.answer(
        "\u0413\u043e\u0442\u043e\u0432\u043e. \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0438\u043c\u043f\u043e\u0440\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u044b.\n"
        "\u26a0\ufe0f \u0415\u0441\u043b\u0438 \u0432 JSON \u0435\u0441\u0442\u044c iCal URL, \u0443\u0431\u0435\u0434\u0438\u0442\u0435\u0441\u044c, \u0447\u0442\u043e \u043e\u043d \u043d\u0435 \u043f\u043e\u043f\u0430\u043b \u0432 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0435 \u0447\u0430\u0442\u044b/\u043b\u043e\u0433\u0438."
    )

