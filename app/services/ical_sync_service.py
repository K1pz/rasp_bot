import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import settings as env_settings
from app.db.connection import async_session_maker
from app.db.models import ScheduleItem
from app.db.repos.schedule_repo import ScheduleRepo
from app.db.repos.settings_repo import SettingsRepo, resolve_ical_url
from app.db.repos.uploads_repo import UploadsRepo
from app.ical.fetcher import fetch_ical, IcalFetchError
from app.ical.parser import parse_ical

logger = logging.getLogger(__name__)

_min_interval_seconds = max(0, int(env_settings.ICAL_SYNC_MIN_INTERVAL_SECONDS or 0))
_sync_days = max(1, int(env_settings.ICAL_SYNC_DAYS or 14))


async def sync_ical_schedule(chat_id: int, force: bool = False) -> bool:
    if not chat_id:
        return False

    now = datetime.now()
    async with async_session_maker() as session:
        settings_repo = SettingsRepo(session)
        db_settings = await settings_repo.get_settings(chat_id)
        ical_url = resolve_ical_url(db_settings)
        if not ical_url:
            return False
        tz_name = db_settings.timezone if db_settings and db_settings.timezone else env_settings.TZ
        try:
            tzinfo = ZoneInfo(tz_name)
        except Exception:
            tzinfo = ZoneInfo("UTC")
        today = datetime.now(tzinfo).date()
        window_start = today
        window_end = today + timedelta(days=_sync_days - 1)

        last_sync_at = None
        if db_settings and db_settings.last_ical_sync_at:
            try:
                last_sync_at = datetime.fromisoformat(db_settings.last_ical_sync_at)
            except ValueError:
                logger.warning(
                    "Invalid last_ical_sync_at for chat_id=%s: %s",
                    chat_id,
                    db_settings.last_ical_sync_at,
                )

        if not force and last_sync_at:
            delta = (now - last_sync_at).total_seconds()
            if delta < _min_interval_seconds:
                return False

        try:
            logger.info("iCal sync started for chat_id=%s url=%s", chat_id, ical_url)
            ics_text = await asyncio.to_thread(fetch_ical, ical_url)
            parsed = await asyncio.to_thread(parse_ical, ics_text, tz_name, window_start, window_end)
        except IcalFetchError as exc:
            logger.error("iCal fetch failed: %s", exc)
            return False
        except Exception:
            logger.exception("iCal parse failed")
            return False

        if parsed.warnings:
            logger.warning(
                "iCal parse warnings (%s): %s",
                len(parsed.warnings),
                "; ".join(parsed.warnings),
            )
        if parsed.warnings and not parsed.items:
            logger.error("iCal parse returned no events, aborting sync to keep existing data.")
            return False

        date_from = window_start.isoformat()
        date_to = window_end.isoformat()

        items = [
            ScheduleItem(
                date=item.date,
                start_time=item.start_time,
                end_time=item.end_time,
                subject=item.subject,
                room=item.room,
                teacher=item.teacher,
                ical_uid=item.ical_uid,
                ical_dtstart=item.ical_dtstart,
            )
            for item in parsed.items
            if date_from <= item.date <= date_to
        ]

        uploaded_at = datetime.now().isoformat()
        warnings_text = "\n".join(parsed.warnings) if parsed.warnings else None

        uploads_repo = UploadsRepo(session)
        schedule_repo = ScheduleRepo(session)
        upload_id = await uploads_repo.insert_upload(
            chat_id=chat_id,
            filename="ical",
            uploaded_by=None,
            uploaded_at=uploaded_at,
            date_from=date_from,
            date_to=date_to,
            rows_count=len(items),
            warnings=warnings_text,
        )
        await schedule_repo.upsert_ical_range(chat_id, date_from, date_to, items, upload_id)
        if db_settings:
            db_settings.last_ical_sync_at = now.isoformat()
            db_settings.coverage_end_date = date_to
            db_settings.updated_at = now.isoformat()
        await session.commit()

    logger.info(
        "iCal sync completed for chat_id=%s (%s..%s, items=%s).",
        chat_id,
        date_from,
        date_to,
        len(items),
    )
    return True
