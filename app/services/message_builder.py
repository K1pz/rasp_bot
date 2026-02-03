import html
from datetime import date, timedelta
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
    if not items:
        lines.append("Занятий нет 🎉")
    else:
        for item in items:
            start_time = html.escape(str(item.start_time)) if item.start_time is not None else ""
            end_time = html.escape(str(item.end_time)) if item.end_time is not None else ""
            time_str = f"{start_time}-{end_time}".strip("-")

            block_lines: list[str] = []
            block_lines.append(f"🕘 {time_str}".rstrip())

            if item.subject:
                block_lines.append(html.escape(str(item.subject)))

            if item.teacher:
                teacher = html.escape(str(item.teacher))
                block_lines.append(f"Преподаватель: {teacher}")

            if item.room:
                block_lines.append(f"🏛 {html.escape(str(item.room))}")

            lines.append("\n".join(block_lines).rstrip())

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
