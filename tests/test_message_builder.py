import pytest
import re
from datetime import date
from app.services.message_builder import (
    build_day_message,
    build_range_message,
    build_week_brief_message,
    build_week_range_message,
    split_telegram,
)
from app.db.models import ScheduleItem

def test_build_day_message_no_items():
    d = date(2023, 10, 1) # Sunday
    msg = build_day_message(d, [], "Europe/Moscow")
    
    # Check header
    assert "📅 01.10.2023 Воскресенье" in msg
    # Check empty message
    assert "Занятий нет 🎉" in msg

def test_build_day_message_items():
    d = date(2023, 10, 2) # Monday
    items = [
        ScheduleItem(
            date="2023-10-02",
            start_time="09:00<",
            end_time="10:30&",
            room="101",
            subject="Math & Logic", # Special char &
            teacher="<Mr. X>" # Special chars < >
        )
    ]
    
    msg = build_day_message(d, items, "Europe/Moscow")
    
    assert "📅 02.10.2023 Понедельник" in msg
    assert "🕘 09:00&lt;-10:30&amp;" in msg
    assert "🏛 101" in msg
    assert "Преподаватель: &lt;Mr. X&gt;" in msg
    # Check escaping
    assert "Math &amp; Logic" in msg
    # Original chars should NOT be present
    assert "<Mr. X>" not in msg
    assert "09:00<" not in msg
    assert "10:30&amp;" in msg
    assert re.search(r"10:30&(?!amp;)", msg) is None

def test_build_day_message_escapes_start_end_time():
    d = date(2023, 10, 3) # Tuesday
    items = [
        ScheduleItem(
            date="2023-10-03",
            start_time="08:00<",
            end_time="09:00>",
            room="101",
            subject="Math",
            teacher="Teacher",
        )
    ]

    msg = build_day_message(d, items, "Europe/Moscow")

    assert "🕘 08:00&lt;-09:00&gt;" in msg
    assert "08:00<" not in msg
    assert "09:00>" not in msg

def test_split_telegram_short():
    text = "Short message"
    chunks = split_telegram(text, limit=4096)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_split_telegram_long():
    # Create text > 10 chars, limit 10
    limit = 10
    line1 = "12345\n" # 6 chars
    line2 = "6789012\n" # 8 chars
    text = line1 + line2 # 14 chars
    
    # Logic:
    # 1. current_chunk = "12345\n" (6)
    # 2. line = "6789012\n" (8)
    # 6+8 = 14 > 10. Flush current.
    # Chunk 1: "12345\n"
    # current_chunk = "6789012\n". 
    # 8 <= 10? Yes.
    # Final flush: "6789012\n"
    
    chunks = split_telegram(text, limit=10)
    assert len(chunks) == 2
    assert chunks[0] == "12345\n"
    assert chunks[1] == "6789012\n"

def test_split_telegram_very_long_line():
    limit = 5
    text = "1234567890" # 10 chars, no newline
    
    chunks = split_telegram(text, limit=5)
    assert len(chunks) == 2
    assert chunks[0] == "12345"
    assert chunks[1] == "67890"


def test_build_range_message_includes_each_day():
    date_from = date(2023, 10, 2)  # Monday
    date_to = date(2023, 10, 4)  # Wednesday

    items = [
        ScheduleItem(
            date="2023-10-02",
            start_time="09:00",
            end_time="10:00",
            room="101",
            subject="Math",
            teacher="Teacher",
        ),
        ScheduleItem(
            date="2023-10-04",
            start_time="11:00",
            end_time="12:00",
            room="202",
            subject="Physics",
            teacher="Teacher 2",
        ),
    ]

    msg = build_range_message(date_from, date_to, items, "Europe/Moscow")

    # Contains headers for each date in the window (including the empty day 03.10.2023)
    assert "02.10.2023" in msg
    assert "03.10.2023" in msg
    assert "04.10.2023" in msg
    assert "Math" in msg
    assert "Physics" in msg


def test_build_week_range_message_summary_and_day_blocks():
    date_from = date(2023, 10, 2)  # Monday
    date_to = date(2023, 10, 7)  # Saturday

    items = [
        ScheduleItem(
            date="2023-10-02",
            start_time="09:00",
            end_time="10:00",
            room="101",
            subject="Math",
            teacher="Teacher",
        ),
        ScheduleItem(
            date="2023-10-04",
            start_time="11:00",
            end_time="12:00",
            room="202",
            subject="Physics",
            teacher="Teacher 2",
        ),
        ScheduleItem(
            date="2023-10-07",
            start_time="18:10",
            end_time="20:00",
            room="303",
            subject="PE",
            teacher="Coach",
        ),
    ]

    msg = build_week_range_message(date_from, date_to, items, "Europe/Moscow")

    lines = msg.splitlines()
    assert lines[0] == "Пн🟧  Вт🟩  Ср🟧  Чт🟩  Пт🟩  Сб🟧"
    assert lines[1] == "Пн 10:00, Ср 12:00, Сб 20:00"

    # No "top frame" separator line; only underline under weekday
    assert "━━━━━━━━━━━━━━" not in lines
    assert "📅 Понедельник (02.10)" in msg
    assert f"  {'━' * len('Понедельник')}" in msg
    assert "📅 Суббота (07.10)" in msg
    assert f"  {'━' * len('Суббота')}" in msg


def test_build_week_brief_message_matches_week_prefix():
    date_from = date(2023, 10, 2)  # Monday
    date_to = date(2023, 10, 7)  # Saturday

    items = [
        ScheduleItem(
            date="2023-10-02",
            start_time="09:00",
            end_time="10:00",
            room="101",
            subject="Math",
            teacher="Teacher",
        ),
        ScheduleItem(
            date="2023-10-04",
            start_time="11:00",
            end_time="12:00",
            room="202",
            subject="Physics",
            teacher="Teacher 2",
        ),
    ]

    brief = build_week_brief_message(date_from, date_to, items, "Europe/Moscow")
    full = build_week_range_message(date_from, date_to, items, "Europe/Moscow")

    assert full.startswith(brief + "\n\n")
    assert len(brief.splitlines()) == 2
