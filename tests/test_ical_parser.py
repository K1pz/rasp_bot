from datetime import date
from pathlib import Path
import textwrap

from app.ical.parser import parse_ical


def test_parse_ical_fixture():
    ics_path = Path(__file__).parent / "fixtures" / "sample.ics"
    ics_text = ics_path.read_text(encoding="utf-8")

    parsed = parse_ical(ics_text, "UTC")

    assert len(parsed.items) == 2
    assert parsed.warnings == []
    assert parsed.date_from == "2026-01-24"
    assert parsed.date_to == "2026-01-25"

    first = parsed.items[0]
    assert first.date == "2026-01-24"
    assert first.start_time == "09:00"
    assert first.end_time == "10:30"
    assert first.subject == "Math"
    assert first.room == "Room 101"
    assert first.teacher == "Prof X"
    assert first.ical_uid == "evt-1"

    second = parsed.items[1]
    assert second.date == "2026-01-25"
    assert second.start_time == "13:00"
    assert second.end_time == "14:30"
    assert second.subject == "Physics"
    assert second.room == "Lab 2"
    assert second.teacher == "Prof Y"
    assert second.ical_uid == "evt-2"


def test_parse_ical_bad_payload():
    parsed = parse_ical("not-ical", "UTC")

    assert parsed.items == []
    assert any("Failed to parse VCALENDAR" in warning for warning in parsed.warnings)


def test_parse_ical_empty_payload():
    parsed = parse_ical("", "UTC")

    assert parsed.items == []
    assert any("Empty iCal payload" in warning for warning in parsed.warnings)


def test_parse_ical_sorts_by_date_and_time():
    ics_text = textwrap.dedent(
        """
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VEVENT
        UID:evt-late
        DTSTART:20260124T150000Z
        DTEND:20260124T160000Z
        SUMMARY:Later on day 1
        END:VEVENT
        BEGIN:VEVENT
        UID:evt-early
        DTSTART:20260124T090000Z
        DTEND:20260124T100000Z
        SUMMARY:Early on day 1
        END:VEVENT
        BEGIN:VEVENT
        UID:evt-nextday
        DTSTART:20260125T070000Z
        DTEND:20260125T080000Z
        SUMMARY:Next day
        END:VEVENT
        END:VCALENDAR
        """
    ).strip()

    parsed = parse_ical(ics_text, "UTC")

    assert [i.subject for i in parsed.items] == [
        "Early on day 1",
        "Later on day 1",
        "Next day",
    ]
    assert parsed.date_from == "2026-01-24"
    assert parsed.date_to == "2026-01-25"


def test_parse_ical_rrule_with_exdate():
    ics_text = textwrap.dedent(
        """
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VEVENT
        UID:evt-rrule
        DTSTART:20260106T090000Z
        DTEND:20260106T103000Z
        RRULE:FREQ=WEEKLY;COUNT=3
        EXDATE:20260113T090000Z
        SUMMARY:Algebra
        END:VEVENT
        END:VCALENDAR
        """
    ).strip()

    parsed = parse_ical(ics_text, "UTC")

    assert [i.date for i in parsed.items] == ["2026-01-06", "2026-01-20"]
    assert parsed.date_from == "2026-01-06"
    assert parsed.date_to == "2026-01-20"


def test_parse_ical_rrule_respects_window():
    ics_text = textwrap.dedent(
        """
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VEVENT
        UID:evt-open
        DTSTART:20240101T080000Z
        DTEND:20240101T090000Z
        RRULE:FREQ=DAILY
        SUMMARY:Daily Class
        END:VEVENT
        END:VCALENDAR
        """
    ).strip()

    parsed = parse_ical(ics_text, "UTC", date(2026, 1, 1), date(2026, 1, 3))

    assert [i.date for i in parsed.items] == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_parse_ical_treats_group_code_as_group_not_teacher():
    ics_text = textwrap.dedent(
        """
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VEVENT
        UID:evt-group
        DTSTART:20260124T090000Z
        DTEND:20260124T103000Z
        SUMMARY:Math
        DESCRIPTION:Teacher: ВИС33
        END:VEVENT
        END:VCALENDAR
        """
    ).strip()

    parsed = parse_ical(ics_text, "UTC")

    assert len(parsed.items) == 1
    item = parsed.items[0]
    assert item.subject == "Math\nВИС33"
    assert item.teacher is None


def test_parse_ical_prefers_real_teacher_over_group_code():
    ics_text = textwrap.dedent(
        """
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VEVENT
        UID:evt-group2
        DTSTART:20260124T090000Z
        DTEND:20260124T103000Z
        SUMMARY:Math
        DESCRIPTION:Teacher: ВИС33\\nTeacher: Prof X
        END:VEVENT
        END:VCALENDAR
        """
    ).strip()

    parsed = parse_ical(ics_text, "UTC")

    assert len(parsed.items) == 1
    item = parsed.items[0]
    assert item.subject == "Math\nВИС33"
    assert item.teacher == "Prof X"
