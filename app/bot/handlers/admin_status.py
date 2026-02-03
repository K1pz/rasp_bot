from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from datetime import datetime

from app.db.connection import async_session_maker
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url, get_ical_setting_state
from app.db.repos.uploads_repo import UploadsRepo
from app.bot.handlers.admin_menu import BTN_STATUS
from app.bot.handlers.common import get_active_chat_id as _get_active_chat_id

router = Router()


@router.message(Command("status"), F.chat.type == "private")
@router.message(F.text == BTN_STATUS, F.chat.type == "private")
async def admin_status(message: Message, state: FSMContext) -> None:
    chat_id = await _get_active_chat_id(state, message)
    if not chat_id:
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        uploads_repo = UploadsRepo(session)
        schedule_repo = ScheduleRepo(session)

        db_settings = await settings_repo.get_settings(chat_id)
        mode = db_settings.mode
        morning_time = db_settings.morning_time
        evening_time = db_settings.evening_time
        timezone = db_settings.timezone
        ical_url = resolve_ical_url(db_settings)
        last_upload = await uploads_repo.get_last_upload(chat_id)
        last_upload_uploaded_at = last_upload.uploaded_at if last_upload else None
        coverage_min, coverage_max = await schedule_repo.get_coverage_minmax(chat_id)

    last_upload_text = "-"
    if last_upload_uploaded_at:
        try:
            ts = datetime.fromisoformat(last_upload_uploaded_at)
            last_upload_text = ts.strftime("%Y-%m-%d %H:%M")
        except Exception:
            last_upload_text = last_upload_uploaded_at

    coverage_text = "-"
    if coverage_min or coverage_max:
        left = coverage_min or "-"
        right = coverage_max or "-"
        coverage_text = f"{left} .. {right}"

    chat_title = None
    try:
        chat = await message.bot.get_chat(chat_id)
        chat_title = chat.title or chat.full_name
    except Exception:
        chat_title = None

    active_chat_label = "\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0439 \u0447\u0430\u0442: "
    if chat_title:
        active_chat_text = f"{chat_title} (ID: {chat_id})"
    else:
        active_chat_text = f"ID: {chat_id}"

    ical_state = get_ical_setting_state(db_settings)
    if ical_state == "disabled":
        ical_status = "\u043e\u0442\u043a\u043b\u044e\u0447\u0451\u043d"
    elif ical_state == "unset" and ical_url:
        ical_status = "\u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e (.env)"
    else:
        ical_status = "\u0437\u0430\u0434\u0430\u043d" if ical_url else "\u043d\u0435 \u0437\u0430\u0434\u0430\u043d"

    response = (
        "\u0421\u0442\u0430\u0442\u0443\u0441 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043a\n"
        f"{active_chat_label}{active_chat_text}\n"
        f"\u0420\u0435\u0436\u0438\u043c: {mode}\n"
        f"\u0423\u0442\u0440\u043e: {morning_time}\n"
        f"\u0412\u0435\u0447\u0435\u0440: {evening_time or '-'}\n"
        f"\u0427\u0430\u0441\u043e\u0432\u043e\u0439 \u043f\u043e\u044f\u0441: {timezone}\n"
        f"iCal: {ical_status}\n"
        f"\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f: {last_upload_text}\n"
        f"\u041f\u043e\u043a\u0440\u044b\u0442\u0438\u0435 \u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u044f: {coverage_text}"
    )

    await message.answer(response)
