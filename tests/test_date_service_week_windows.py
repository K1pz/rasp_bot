from datetime import date

from app.services.date_service import get_next_week_window_from, get_week_window_from


def test_get_week_window_from_thursday_to_saturday():
    # 2026-02-05 is Thursday
    today = date(2026, 2, 5)
    date_from, date_to = get_week_window_from(today)
    assert date_from == date(2026, 2, 5)
    assert date_to == date(2026, 2, 7)  # Saturday


def test_get_week_window_from_saturday_only():
    today = date(2026, 2, 7)  # Saturday
    date_from, date_to = get_week_window_from(today)
    assert date_from == date(2026, 2, 7)
    assert date_to == date(2026, 2, 7)


def test_get_next_week_window_from_thursday_next_monday_to_saturday():
    # 2026-02-05 is Thursday
    today = date(2026, 2, 5)
    date_from, date_to = get_next_week_window_from(today)
    assert date_from == date(2026, 2, 9)  # next Monday
    assert date_to == date(2026, 2, 14)  # next Saturday


def test_get_next_week_window_from_monday_is_plus_7_days():
    today = date(2026, 2, 2)  # Monday
    date_from, date_to = get_next_week_window_from(today)
    assert date_from == date(2026, 2, 9)
    assert date_to == date(2026, 2, 14)

