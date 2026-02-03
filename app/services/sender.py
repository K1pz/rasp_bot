import logging
from datetime import date, datetime

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.sendlog_repo import SendLogRepo
from app.services.message_builder import build_day_message, split_telegram, ParseMode
from app.services.alerts_service import alert_admin
from app.services.ical_sync_service import sync_ical_schedule


def _format_send_error(exc: Exception) -> str:
    detail = (str(exc) or "").strip() or repr(exc)
    if isinstance(exc, TelegramForbiddenError):
        return f"forbidden: {detail}"
    if isinstance(exc, TelegramBadRequest):
        return f"bad_request: {detail}"
    return detail

async def send_schedule(chat_id: int, target_date: date, kind: str, notify_admin_on_data_gaps: bool = True) -> bool:
    """
    Orchestrates sending a schedule for a specific date to a user.
    Returns True only if the message was successfully sent to Telegram and persisted as status="ok".
    Returns False if skipped (invalid chat_id / duplicate) or if sending failed (status="error").
    """
    async with async_session_maker() as session:
        # 1. Check if chat_id is bound/valid (anti-spam / logic check)
        settings_repo = SettingsRepo(session)
        settings = await settings_repo.get_settings(chat_id)
        if not settings:
            await alert_admin(f"send_schedule called for unknown chat_id {chat_id}")
            return False
        ical_url = resolve_ical_url(settings)

    if ical_url:
        try:
            await sync_ical_schedule(chat_id)
        except Exception:
            logging.exception("Pre-send iCal sync failed; continuing with cached data.")

    async with async_session_maker() as session:
        # 2. Anti-duplicate mechanism
        sendlog_repo = SendLogRepo(session)
        target_date_str = target_date.strftime("%Y-%m-%d")

        # try_reserve returns True if we successfully reserved the task
        if not await sendlog_repo.try_reserve(chat_id, target_date_str, kind):
            logging.info(f"Schedule for {chat_id} on {target_date_str} ({kind}) already reserved/ok/skipped.")
            return False

        try:
            settings_repo = SettingsRepo(session)
            settings = await settings_repo.get_settings(chat_id)

            # 3. Fetch schedule items
            schedule_repo = ScheduleRepo(session)
            items = await schedule_repo.get_by_date(chat_id, target_date_str)

            # 4. Build message
            tz = settings.timezone if settings else env_settings.TZ
            message_text = build_day_message(target_date, items, tz)

            # 5. Send to Telegram
            chunks = split_telegram(message_text)

            # Lazy import to avoid circular dependencies and because bot might not be init yet
            from app.bot.dispatcher import bot

            for chunk in chunks:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)

            # 6. Mark as successfully sent
            sent_at = datetime.now().isoformat()
            await sendlog_repo.mark_sent(chat_id, target_date_str, kind, sent_at)
            await session.commit()

        except Exception as exc:
            error_text = _format_send_error(exc)
            # We must not leave the task in "reserved" state on any failure, otherwise retries get blocked.
            logging.exception("Failed to send schedule to chat_id=%s kind=%s date=%s: %s", chat_id, kind, target_date_str, error_text)
            try:
                await sendlog_repo.mark_error(chat_id, target_date_str, kind, error_text)
                await session.commit()
            except Exception:
                # If DB write failed, scheduler will see a stuck "reserved" task (or none) and retry later.
                logging.exception("Failed to persist send_log error (chat_id=%s kind=%s date=%s).", chat_id, kind, target_date_str)
            return False

        # 7. Check regarding data coverage gaps
        if not items and notify_admin_on_data_gaps:
            # We sent "No Classes", check if it's because of missing data (outside coverage)
            min_date, max_date = await schedule_repo.get_coverage_minmax(chat_id)

            is_outside = False
            if not min_date or not max_date:
                is_outside = True
            else:
                if target_date_str < min_date or target_date_str > max_date:
                    is_outside = True

            if is_outside:
                await alert_admin(
                    f"User received 'No Classes' for {target_date_str}, but date is outside DB coverage "
                    f"({min_date}..{max_date}). Might be missing upload?"
                )

        return True
