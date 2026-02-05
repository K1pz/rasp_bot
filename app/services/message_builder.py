import html
from datetime import date, datetime, time, timedelta
from app.db.models import ScheduleItem

class ParseMode:
    HTML = "HTML"

WEEKDAYS = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}

WEEKDAY_ABBRS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}

WEEK_SEPARATOR = "━━━━━━━━━━━━━━"

STATUS_HAS_CLASSES = "🟧"
STATUS_NO_CLASSES = "🟩"


def _looks_like_group_code(value: str) -> bool:
    raw = (value or "").strip()
    if not raw or " " in raw:
        return False
    if len(raw) > 24:
        return False
    has_digit = any(ch.isdigit() for ch in raw)
    has_letter = any(ch.isalpha() for ch in raw)
    if not (has_digit and has_letter):
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя0123456789-_.")
    return all(ch in allowed for ch in raw)


def _parse_hhmm(value: str) -> time | None:
    raw = (value or "").strip()
    if len(raw) >= 5:
        raw = raw[:5]
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except Exception:
        return None


def _build_day_body(items: list[ScheduleItem]) -> str:
    lines: list[str] = []
    if not items:
        return "Занятий нет 🎉"

    for item in items:
        start_time = html.escape(str(item.start_time)) if item.start_time is not None else ""
        end_time = html.escape(str(item.end_time)) if item.end_time is not None else ""
        time_str = f"{start_time}-{end_time}".strip("-")

        block_lines: list[str] = []
        block_lines.append(f"🕘 {time_str}".rstrip())

        subject = str(item.subject).strip() if item.subject else ""
        teacher_raw = str(item.teacher).strip() if item.teacher else ""

        group_line: str | None = None
        teacher_line: str | None = teacher_raw or None
        if teacher_raw and _looks_like_group_code(teacher_raw):
            group_line = teacher_raw
            teacher_line = None

        if subject:
            block_lines.append(html.escape(subject))
            if group_line and group_line not in subject:
                block_lines.append(html.escape(group_line))
        elif group_line:
            block_lines.append(html.escape(group_line))

        if teacher_line:
            teacher = html.escape(teacher_line)
            block_lines.append(f"Преподаватель: {teacher}")

        if item.room:
            block_lines.append(f"🏛 {html.escape(str(item.room))}")

        lines.append("\n".join(block_lines).rstrip())

    return "\n\n".join(lines).strip()


def _get_last_end_time(items: list[ScheduleItem]) -> str | None:
    if not items:
        return None

    parsed: list[tuple[time, str]] = []
    raw_values: list[str] = []
    for item in items:
        if not item.end_time:
            continue
        raw_values.append(str(item.end_time))
        parsed_time = _parse_hhmm(str(item.end_time))
        if parsed_time is not None:
            parsed.append((parsed_time, str(item.end_time)))

    if parsed:
        return max(parsed, key=lambda x: x[0])[1][:5]

    if raw_values:
        return max(raw_values)

    return None


def build_day_message(target_date: date, items: list[ScheduleItem], tz: str) -> str:
    """
    Builds a schedule message for a specific day.
    Format example (Telegram render):
    📅 04.02.2026 Среда

    🕘 08:30-10:05
    лаб Инструментальные средства информационных систем, п/г 2
    ВИС33
    Преподаватель: ст.пр.Барашко Елена Николаевна
    🏛 1-351
    """
    weekday_name = WEEKDAYS.get(target_date.weekday(), target_date.strftime("%A"))
    header = f"📅 {target_date.strftime('%d.%m.%Y')} {weekday_name}"

    lines = []
    lines.append(_build_day_body(items))

    return (header + "\n\n" + "\n\n".join(lines)).strip()

def build_range_message(date_from: date, date_to: date, items: list[ScheduleItem], tz: str) -> str:
    """
    Builds a schedule message for an inclusive date range.
    Always includes every date in the window (even if there are no items for the day).
    """
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    items_by_date: dict[str, list[ScheduleItem]] = {}
    for item in items:
        items_by_date.setdefault(item.date, []).append(item)

    blocks: list[str] = []
    current = date_from
    while current <= date_to:
        day_items = items_by_date.get(current.isoformat(), [])
        blocks.append(build_day_message(current, day_items, tz))
        current = current + timedelta(days=1)

    return "\n\n".join(blocks).strip()


def build_week_range_message(date_from: date, date_to: date, items: list[ScheduleItem], tz: str) -> str:
    """
    Full week message for /week and /nextweek.
    - Title line: "📅 Ваше расписание!"
    - Day blocks include only days that have classes
    """
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    items_by_date: dict[str, list[ScheduleItem]] = {}
    for item in items:
        items_by_date.setdefault(item.date, []).append(item)

    day_list: list[date] = []
    current = date_from
    while current <= date_to:
        day_list.append(current)
        current = current + timedelta(days=1)

    blocks: list[str] = []
    for day in day_list:
        day_items = items_by_date.get(day.isoformat(), [])
        if not day_items:
            continue
        blocks.append(build_day_message(day, day_items, tz))

    title = "📅 Ваше расписание!"
    if not blocks:
        return (title + "\n\n" + "Занятий нет 🎉").strip()

    # Use two blank lines between day blocks for readability.
    return (title + "\n\n" + "\n\n\n".join(blocks)).strip()


def _build_week_summary_lines(
    day_list: list[date],
    items_by_date: dict[str, list[ScheduleItem]],
) -> tuple[str, str]:
    summary_parts: list[str] = []
    busy_parts: list[str] = []
    for day in day_list:
        day_items = items_by_date.get(day.isoformat(), [])
        abbr = WEEKDAY_ABBRS.get(day.weekday(), day.strftime("%a"))
        if day_items:
            summary_parts.append(f"{abbr}{STATUS_HAS_CLASSES}")
            last_end = _get_last_end_time(day_items)
            if last_end:
                busy_parts.append(f"{abbr} {html.escape(last_end)}")
        else:
            summary_parts.append(f"{abbr}{STATUS_NO_CLASSES}")

    summary_line = "  ".join(summary_parts).strip()
    busy_line = ", ".join(busy_parts).strip() if busy_parts else "Занятий нет 🎉"
    return summary_line, busy_line


def build_week_brief_message(date_from: date, date_to: date, items: list[ScheduleItem], tz: str) -> str:
    """
    Summary-only message for /week and /nextweek-like windows:
    - summary line with per-day status (🟩/🟧)
    - second summary line with end time per busy day
    """
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    items_by_date: dict[str, list[ScheduleItem]] = {}
    for item in items:
        items_by_date.setdefault(item.date, []).append(item)

    day_list: list[date] = []
    current = date_from
    while current <= date_to:
        day_list.append(current)
        current = current + timedelta(days=1)

    summary_line, busy_line = _build_week_summary_lines(day_list, items_by_date)
    return (summary_line + "\n" + busy_line).strip()

def split_telegram(text: str, limit: int = 4096) -> list[str]:
    """
    Splits text into chunks of at most `limit` characters, 
    preferring to split at line breaks.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    current_chunk = ""

    # Split by lines, keeping newlines
    lines = text.splitlines(keepends=True)
    
    for line in lines:
        if len(current_chunk) + len(line) > limit:
            # If current chunk is not empty, flush it
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # If the line itself is longer than limit, we have to hard split it
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current_chunk = line
        else:
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
