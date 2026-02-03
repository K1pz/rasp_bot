import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.admin_menu import BTN_UPLOAD
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id
from app.db.connection import async_session_maker
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url
from app.db.repos.uploads_repo import UploadsRepo
from app.services.ical_sync_service import sync_ical_schedule

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("upload"), F.chat.type == "private")
@router.message(F.text == BTN_UPLOAD, F.chat.type == "private")
async def admin_upload(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)
        ical_url = resolve_ical_url(db_settings)

    if not ical_url:
        await message.answer(
            "\u0421\u0441\u044b\u043b\u043a\u0430 iCal \u043d\u0435 \u0437\u0430\u0434\u0430\u043d\u0430. "
            "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 /settings \u0438 \u0443\u043a\u0430\u0436\u0438\u0442\u0435 URL."
        )
        return

    await message.answer(
        "\u0417\u0430\u043f\u0443\u0441\u043a\u0430\u044e \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044e "
        "\u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u043f\u043e iCal..."
    )

    try:
        ok = await sync_ical_schedule(chat_id, force=True)
    except Exception:
        logger.exception("Failed to sync iCal from admin command.")
        await message.answer(
            "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c "
            "\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044e. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 "
            "\u0435\u0449\u0435 \u0440\u0430\u0437."
        )
        return

    if not ok:
        await message.answer(
            "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c "
            "\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044e. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 "
            "\u0441\u0441\u044b\u043b\u043a\u0443 iCal \u0438 \u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430."
        )
        return

    async with async_session_maker() as session:
        uploads_repo = UploadsRepo(session)
        schedule_repo = ScheduleRepo(session)
        last_upload = await uploads_repo.get_last_upload(chat_id)
        coverage_min, coverage_max = await schedule_repo.get_coverage_minmax(chat_id)

    date_range = "?"
    rows_count = "?"
    warnings_preview = None
    warnings_count = 0
    if last_upload:
        if last_upload.date_from or last_upload.date_to:
            left = last_upload.date_from or "?"
            right = last_upload.date_to or "?"
            date_range = f"{left}..{right}"
        if last_upload.rows_count is not None:
            rows_count = str(last_upload.rows_count)
        if last_upload.warnings:
            warning_lines = [line for line in last_upload.warnings.splitlines() if line.strip()]
            warnings_count = len(warning_lines)
            if warning_lines:
                warnings_preview = "\n".join(warning_lines[:5])

    coverage_text = "?"
    if coverage_min or coverage_max:
        left = coverage_min or "?"
        right = coverage_max or "?"
        coverage_text = f"{left} .. {right}"

    response = (
        "\u0413\u043e\u0442\u043e\u0432\u043e.\n"
        f"\u0414\u0438\u0430\u043f\u0430\u0437\u043e\u043d \u0434\u0430\u0442: {date_range}\n"
        f"\u0417\u0430\u0433\u0440\u0443\u0436\u0435\u043d\u043e \u0441\u0442\u0440\u043e\u043a: {rows_count}\n"
        f"\u041f\u043e\u043a\u0440\u044b\u0442\u0438\u0435 \u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u044f: {coverage_text}"
    )
    if warnings_count:
        response += f"\n\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u044f: {warnings_count}"
        if warnings_preview:
            response += f"\n{warnings_preview}"

    await message.answer(response)
