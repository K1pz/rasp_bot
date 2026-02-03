import logging

async def alert_admin(message: str) -> None:
    """
    Logs an admin alert.
    Always logs; no Telegram delivery is configured.
    """
    logging.warning("ADMIN ALERT: %s", message)


async def daily_coverage_check():
    """
    Checks if coverage is running low (based on max date in schedule).
    Alerts admin if max date < today + warn_days.
    """
    from app.db.connection import async_session_maker
    from app.db.repos.schedule_repo import ScheduleRepo
    from app.db.repos.settings_repo import SettingsRepo
    from app.services.date_service import get_today
