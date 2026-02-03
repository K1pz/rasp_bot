import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.models import Settings
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url
from app.db.repos.sendlog_repo import SendLogRepo, is_send_success
from app.services.date_service import get_local_now, get_today, get_tomorrow, parse_hhmm
from app.services.ical_sync_service import sync_ical_schedule
from app.services.sender import send_schedule

scheduler = AsyncIOScheduler()


def init_scheduler(timezone: str = "Europe/Moscow"):
    """
    Initialize the scheduler configuration.
    """
    if not scheduler.running:
        scheduler.configure(timezone=timezone)
        # We start() it in main.py usually, or here.
        # But commonly we might want to add jobs before starting.
        # Let's just ensure timezone is set.


def _job_id(prefix: str) -> str:
    return f"{prefix}"


def _is_ical_stale(last_sync_at: str | None, min_interval_seconds: int) -> bool:
    if min_interval_seconds <= 0:
        return True
    if not last_sync_at:
        return True
    try:
        last_sync_dt = datetime.fromisoformat(last_sync_at)
    except ValueError:
        return True
    delta = (datetime.now() - last_sync_dt).total_seconds()
    return delta >= min_interval_seconds


async def _update_last_sent(chat_id: int, **updates: str) -> None:
    if not updates:
        return
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        await settings_repo.upsert_settings(chat_id, **updates)
        await session.commit()


async def _get_sendlog_status(chat_id: int, target_date: str, kind: str) -> str | None:
    async with async_session_maker() as session:
        sendlog_repo = SendLogRepo(session)
        log = await sendlog_repo.get_log(chat_id, target_date, kind)
        return log.status if log else None


async def _run_periodic_sender() -> None:
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        all_settings = await settings_repo.get_all_settings()

    min_interval_seconds = max(0, int(env_settings.ICAL_SYNC_MIN_INTERVAL_SECONDS or 0))

    for settings in all_settings:
        if not settings.chat_id:
            continue
        try:
            mode = int(settings.mode)
        except (TypeError, ValueError):
            logging.warning("Scheduler: invalid mode=%r for chat_id=%s", settings.mode, settings.chat_id)
            continue
        if mode == 0:
            continue

        tz = settings.timezone or env_settings.TZ
        now_local = get_local_now(tz)
        today = get_today(tz)
        today_str = today.isoformat()

        updates: dict[str, str] = {}

        morning_due = False
        if mode >= 1:
            if settings.morning_time:
                try:
                    morning_time = parse_hhmm(settings.morning_time)
                    if now_local.time() >= morning_time:
                        morning_status = await _get_sendlog_status(settings.chat_id, today_str, "morning")
                        morning_due = not is_send_success(morning_status)
                        if is_send_success(morning_status) and settings.last_sent_morning_date != today_str:
                            updates["last_sent_morning_date"] = today_str
                except ValueError:
                    logging.error("Invalid morning_time format: %s (chat_id=%s)", settings.morning_time, settings.chat_id)

        evening_due = False
        if mode == 2 and settings.evening_time:
            try:
                evening_time = parse_hhmm(settings.evening_time)
                if now_local.time() >= evening_time:
                    tomorrow = get_tomorrow(tz)
                    tomorrow_str = tomorrow.isoformat()
                    evening_status = await _get_sendlog_status(settings.chat_id, tomorrow_str, "evening")
                    evening_due = not is_send_success(evening_status)
                    if is_send_success(evening_status) and settings.last_sent_evening_date != today_str:
                        updates["last_sent_evening_date"] = today_str
            except ValueError:
                logging.error("Invalid evening_time format: %s (chat_id=%s)", settings.evening_time, settings.chat_id)

        if not morning_due and not evening_due:
            if updates:
                await _update_last_sent(settings.chat_id, **updates)
            continue

        effective_ical_url = resolve_ical_url(settings)
        if effective_ical_url and _is_ical_stale(settings.last_ical_sync_at, min_interval_seconds):
            try:
                await sync_ical_schedule(settings.chat_id)
            except Exception:
                logging.exception("iCal sync failed for chat_id=%s; proceeding with cached data.", settings.chat_id)

        if morning_due:
            await send_schedule(settings.chat_id, today, "morning")
            morning_status = await _get_sendlog_status(settings.chat_id, today_str, "morning")
            if is_send_success(morning_status):
                updates["last_sent_morning_date"] = today_str

        if evening_due:
            tomorrow = get_tomorrow(tz)
            tomorrow_str = tomorrow.isoformat()
            await send_schedule(settings.chat_id, tomorrow, "evening")
            evening_status = await _get_sendlog_status(settings.chat_id, tomorrow_str, "evening")
            if is_send_success(evening_status):
                updates["last_sent_evening_date"] = today_str

        await _update_last_sent(settings.chat_id, **updates)


def ensure_periodic_job() -> None:
    scheduler.add_job(
        _run_periodic_sender,
        IntervalTrigger(minutes=1),
        id=_job_id("periodic_sender"),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )


def apply_schedule(settings: Settings):
    """
    Compatibility hook: per-chat scheduling is replaced with a single periodic job.
    """
    if not settings or not settings.chat_id:
        logging.warning("Scheduler: chat_id is missing, skipping job creation.")
        return
    ensure_periodic_job()
