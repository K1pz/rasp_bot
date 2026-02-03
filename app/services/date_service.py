from datetime import datetime, date, time, timedelta
import zoneinfo

def get_local_now(tz: str) -> datetime:
    return datetime.now(zoneinfo.ZoneInfo(tz))

def get_today(tz: str) -> date:
    return get_local_now(tz).date()

def get_tomorrow(tz: str) -> date:
    return get_today(tz) + timedelta(days=1)

def get_week_window_from(today: date) -> tuple[date, date]:
    """
    Returns an inclusive window for "this week" schedule relative to `today`.

    Project convention: academic week is Monday..Saturday.
    - start: `today`
    - end: ближайшая суббота в пределах этой недели (если сегодня воскресенье — только сегодня)
    """
    # Monday=0 .. Sunday=6, Saturday=5
    if today.weekday() <= 5:
        return today, today + timedelta(days=(5 - today.weekday()))
    return today, today

def get_next_week_window_from(today: date) -> tuple[date, date]:
    """
    Returns an inclusive window for "next week" schedule relative to `today`.

    Project convention: academic week is Monday..Saturday.
    - start: next Monday relative to `today`
    - end: next Saturday relative to `today`
    """
    # Days until next Monday (Monday -> 7, Sunday -> 1)
    days_until_next_monday = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_until_next_monday)
    end = start + timedelta(days=5)
    return start, end

def get_week_window(tz: str) -> tuple[date, date]:
    return get_week_window_from(get_today(tz))

def get_next_week_window(tz: str) -> tuple[date, date]:
    return get_next_week_window_from(get_today(tz))

def parse_hhmm(hhmm: str) -> time:
    return datetime.strptime(hhmm, "%H:%M").time()
