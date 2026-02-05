import logging
import re
from datetime import date, datetime, time as dt_time, timedelta
from typing import Optional, List, Iterable
from zoneinfo import ZoneInfo

from icalendar import Calendar
from dateutil import rrule as dateutil_rrule

from app.schedule.models import ParsedItem, ParsedSchedule

logger = logging.getLogger(__name__)

DEFAULT_RECURRENCE_WINDOW_DAYS = 366
MAX_RECURRENCE_OCCURRENCES = 5000


_GROUP_CODE_RE = re.compile(
    r"^(?=.*[A-Za-zА-Яа-яЁё])(?=.*\d)[A-Za-zА-Яа-яЁё\d][A-Za-zА-Яа-яЁё\d_\-./]{1,30}$"
)


def _looks_like_group_code(value: str) -> bool:
    raw = (value or "").strip()
    if not raw or " " in raw:
        return False
    # Keep it conservative: avoid treating long free text as a group.
    if len(raw) > 24:
        return False
    return bool(_GROUP_CODE_RE.match(raw))


def parse_ical(
    ical_text: str,
    default_tz: str,
    window_start: Optional[date] = None,
    window_end: Optional[date] = None,
) -> ParsedSchedule:
    items: List[ParsedItem] = []
    warnings: List[str] = []

    if not ical_text:
        warnings.append("Empty iCal payload.")
        return ParsedSchedule(items=[], warnings=warnings, date_from=None, date_to=None)

    try:
        cal = Calendar.from_ical(ical_text)
    except Exception as exc:
        warnings.append(f"Failed to parse VCALENDAR: {exc}")
        return ParsedSchedule(items=[], warnings=warnings, date_from=None, date_to=None)

    try:
        tz = ZoneInfo(default_tz)
    except Exception as exc:
        warnings.append(f"Invalid timezone '{default_tz}', falling back to UTC: {exc}")
        tz = ZoneInfo("UTC")

    overrides = _collect_recurrence_overrides(cal, tz)

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        if _is_cancelled(component):
            continue

        uid = _as_text(component.get("uid")) or "unknown"

        if component.get("recurrence-id") is not None:
            _append_single_event(
                items=items,
                warnings=warnings,
                component=component,
                uid=uid,
                tz=tz,
            )
            continue

        dtstart_raw = _get_dt(component, "dtstart")
        if dtstart_raw is None:
            warnings.append(f"Event {uid}: missing DTSTART")
            continue

        if _is_date_only(dtstart_raw):
            warnings.append(f"Event {uid}: DTSTART is date-only, skipping")
            continue

        dtend_raw = _get_dt(component, "dtend")
        if dtend_raw is None:
            duration = component.get("duration")
            if duration is not None and isinstance(duration.dt, timedelta):
                dtend_raw = dtstart_raw + duration.dt
            else:
                warnings.append(f"Event {uid}: missing DTEND/DURATION")
                continue

        if _is_date_only(dtend_raw):
            warnings.append(f"Event {uid}: DTEND is date-only, skipping")
            continue

        dtstart = _to_tz_aware(dtstart_raw, tz)
        dtend = _to_tz_aware(dtend_raw, tz)
        if dtstart is None or dtend is None:
            warnings.append(f"Event {uid}: invalid datetime values")
            continue

        duration = dtend - dtstart
        if duration <= timedelta(0):
            warnings.append(f"Event {uid}: DTEND <= DTSTART, skipping")
            continue

        subject, room, teacher = _extract_event_fields(component)

        if _has_recurrence(component):
            occurrences = _expand_recurrences(
                component=component,
                uid=uid,
                dtstart=dtstart,
                tz=tz,
                window_start=window_start,
                window_end=window_end,
                excluded=overrides.get(uid),
                warnings=warnings,
            )
            for occ_start in occurrences:
                occ_end = occ_start + duration
                if occ_end <= occ_start:
                    continue
                items.append(
                    ParsedItem(
                        date=occ_start.strftime("%Y-%m-%d"),
                        start_time=occ_start.strftime("%H:%M"),
                        end_time=occ_end.strftime("%H:%M"),
                        subject=subject,
                        room=room,
                        teacher=teacher,
                        ical_uid=uid,
                        ical_dtstart=occ_start.isoformat(),
                    )
                )
        else:
            items.append(
                ParsedItem(
                    date=dtstart.strftime("%Y-%m-%d"),
                    start_time=dtstart.strftime("%H:%M"),
                    end_time=dtend.strftime("%H:%M"),
                    subject=subject,
                    room=room,
                    teacher=teacher,
                    ical_uid=uid,
                    ical_dtstart=dtstart.isoformat(),
                )
            )

    # Deduplicate and sort
    unique_items = []
    seen = set()
    for it in items:
        identity = (
            it.ical_uid or "",
            it.ical_dtstart or "",
            it.date,
            it.start_time,
            it.end_time,
            it.subject,
            it.room or "",
            it.teacher or "",
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique_items.append(it)

    unique_items.sort(key=lambda x: (x.date, x.start_time))

    date_from = None
    date_to = None
    if unique_items:
        all_dates = [it.date for it in unique_items]
        date_from = min(all_dates)
        date_to = max(all_dates)

    return ParsedSchedule(items=unique_items, warnings=warnings, date_from=date_from, date_to=date_to)


def _get_dt(component, key: str) -> Optional[datetime]:
    prop = component.get(key)
    if prop is None:
        return None
    return prop.dt


def _is_date_only(value) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _to_tz_aware(value: datetime, tz: ZoneInfo) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _as_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _collapse_text(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned = [line.strip() for line in lines if line.strip()]
    return " / ".join(cleaned)


def _is_cancelled(component) -> bool:
    status = _as_text(component.get("status"))
    return status is not None and status.upper() == "CANCELLED"


def _extract_event_fields(component) -> tuple[str, Optional[str], Optional[str]]:
    subject = _as_text(component.get("summary")) or "Предмет не указан"
    room = _as_text(component.get("location"))
    description = _as_text(component.get("description"))
    parsed_room, parsed_teacher, parsed_group, free_text = _parse_description_fields(description)

    if not room:
        room = parsed_room

    teacher = None
    if parsed_teacher and not _looks_like_group_code(parsed_teacher):
        teacher = parsed_teacher
    elif free_text:
        collapsed = _collapse_text("\n".join(free_text))
        if _looks_like_group_code(collapsed):
            parsed_group = parsed_group or collapsed
        elif collapsed:
            teacher = collapsed

    if not teacher:
        organizer_teacher = _extract_teacher_from_organizer(component)
        if organizer_teacher:
            teacher = organizer_teacher

    if parsed_group and subject and parsed_group not in subject:
        subject = f"{subject}\n{parsed_group}"

    return subject, room, teacher


def _extract_teacher_from_organizer(component) -> Optional[str]:
    organizer = component.get("organizer")
    if organizer is None:
        return None

    try:
        params = getattr(organizer, "params", None)
        cn = None if not params else (params.get("CN") or params.get("cn"))
        if isinstance(cn, list):
            cn = cn[0] if cn else None
        if cn is not None:
            value = str(cn).strip()
            if value and not _looks_like_group_code(value):
                return value
    except Exception:
        pass

    return None


def _append_single_event(
    items: list[ParsedItem],
    warnings: list[str],
    component,
    uid: str,
    tz: ZoneInfo,
) -> None:
    dtstart_raw = _get_dt(component, "dtstart")
    if dtstart_raw is None:
        warnings.append(f"Event {uid}: missing DTSTART")
        return

    if _is_date_only(dtstart_raw):
        warnings.append(f"Event {uid}: DTSTART is date-only, skipping")
        return

    dtend_raw = _get_dt(component, "dtend")
    if dtend_raw is None:
        duration = component.get("duration")
        if duration is not None and isinstance(duration.dt, timedelta):
            dtend_raw = dtstart_raw + duration.dt
        else:
            warnings.append(f"Event {uid}: missing DTEND/DURATION")
            return

    if _is_date_only(dtend_raw):
        warnings.append(f"Event {uid}: DTEND is date-only, skipping")
        return

    dtstart = _to_tz_aware(dtstart_raw, tz)
    dtend = _to_tz_aware(dtend_raw, tz)
    if dtstart is None or dtend is None:
        warnings.append(f"Event {uid}: invalid datetime values")
        return

    if dtend <= dtstart:
        warnings.append(f"Event {uid}: DTEND <= DTSTART, skipping")
        return

    subject, room, teacher = _extract_event_fields(component)
    items.append(
        ParsedItem(
            date=dtstart.strftime("%Y-%m-%d"),
            start_time=dtstart.strftime("%H:%M"),
            end_time=dtend.strftime("%H:%M"),
            subject=subject,
            room=room,
            teacher=teacher,
            ical_uid=uid,
            ical_dtstart=dtstart.isoformat(),
        )
    )


def _collect_recurrence_overrides(cal: Calendar, tz: ZoneInfo) -> dict[str, set[datetime]]:
    overrides: dict[str, set[datetime]] = {}
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        if component.get("recurrence-id") is None:
            continue
        uid = _as_text(component.get("uid")) or "unknown"
        rid_raw = _get_dt(component, "recurrence-id")
        if rid_raw is None or _is_date_only(rid_raw):
            continue
        rid = _to_tz_aware(rid_raw, tz)
        if rid is None:
            continue
        overrides.setdefault(uid, set()).add(rid)
    return overrides


def _has_recurrence(component) -> bool:
    return bool(component.get("rrule") or component.get("rdate"))


def _expand_recurrences(
    component,
    uid: str,
    dtstart: datetime,
    tz: ZoneInfo,
    window_start: Optional[date],
    window_end: Optional[date],
    excluded: Optional[set[datetime]],
    warnings: list[str],
) -> list[datetime]:
    rset = dateutil_rrule.rruleset()
    rrule_props = component.get("rrule")
    rule_strings: list[str] = []

    if rrule_props:
        rule_items = rrule_props if isinstance(rrule_props, list) else [rrule_props]
        for rule in rule_items:
            rule_str = _rrule_to_str(rule)
            if not rule_str:
                continue
            rule_strings.append(rule_str)
            try:
                rset.rrule(dateutil_rrule.rrulestr(rule_str, dtstart=dtstart))
            except Exception as exc:
                warnings.append(f"Event {uid}: failed to parse RRULE '{rule_str}': {exc}")

    for rdate in _iter_rule_datetimes(component.get("rdate"), tz, uid, "RDATE", warnings):
        rset.rdate(rdate)

    if not rrule_props and component.get("rdate"):
        rset.rdate(dtstart)

    for exdate in _iter_rule_datetimes(component.get("exdate"), tz, uid, "EXDATE", warnings):
        rset.exdate(exdate)

    if excluded:
        for ex in excluded:
            rset.exdate(ex)

    if not rule_strings and not component.get("rdate"):
        return [dtstart]

    start_dt, end_dt = _resolve_recurrence_window(dtstart, window_start, window_end, rule_strings)

    if start_dt and end_dt:
        occurrences = list(rset.between(start_dt, end_dt, inc=True))
    else:
        occurrences = list(rset)

    if len(occurrences) > MAX_RECURRENCE_OCCURRENCES:
        warnings.append(
            f"Event {uid}: recurrence expanded to {len(occurrences)} items, "
            f"capped at {MAX_RECURRENCE_OCCURRENCES}"
        )
        occurrences = occurrences[:MAX_RECURRENCE_OCCURRENCES]

    return occurrences


def _rrule_to_str(rule) -> Optional[str]:
    try:
        if hasattr(rule, "to_ical"):
            data = rule.to_ical()
            if isinstance(data, bytes):
                return data.decode("utf-8")
            return str(data)
        return str(rule)
    except Exception:
        return None


def _resolve_recurrence_window(
    dtstart: datetime,
    window_start: Optional[date],
    window_end: Optional[date],
    rule_strings: list[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    if window_start and window_end:
        start_dt = datetime.combine(window_start, dt_time.min, tzinfo=dtstart.tzinfo)
        end_dt = datetime.combine(window_end, dt_time.max, tzinfo=dtstart.tzinfo)
        return start_dt, end_dt

    has_infinite = False
    for rule in rule_strings:
        normalized = rule.upper()
        if "COUNT=" not in normalized and "UNTIL=" not in normalized:
            has_infinite = True
            break

    if has_infinite:
        return dtstart, dtstart + timedelta(days=DEFAULT_RECURRENCE_WINDOW_DAYS)

    return None, None


def _iter_rule_datetimes(
    prop,
    tz: ZoneInfo,
    uid: str,
    label: str,
    warnings: list[str],
) -> Iterable[datetime]:
    if not prop:
        return []

    values = prop if isinstance(prop, list) else [prop]
    dates: list[datetime] = []

    for value in values:
        if hasattr(value, "dts"):
            dts = value.dts
        else:
            dts = [value]

        for entry in dts:
            raw = entry.dt if hasattr(entry, "dt") else entry
            if _is_date_only(raw):
                warnings.append(f"Event {uid}: {label} is date-only, skipping")
                continue
            normalized = _to_tz_aware(raw, tz)
            if normalized is None:
                warnings.append(f"Event {uid}: {label} has invalid datetime, skipping")
                continue
            dates.append(normalized)

    return dates


def _parse_description_fields(
    description: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str], list[str]]:
    if not description:
        return None, None, None, []

    teacher = None
    room = None
    group = None
    free_text: list[str] = []

    teacher_keys = {"преподаватель", "преп", "teacher", "lecturer", "instructor"}
    group_keys = {"группа", "group", "grp", "гр"}
    room_keys = {"аудитория", "ауд", "кабинет", "room", "location"}

    lines = description.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        cleaned = line.strip().replace("\t", " ")
        if not cleaned:
            continue

        if ":" in cleaned:
            key, value = cleaned.split(":", 1)
        elif " - " in cleaned:
            key, value = cleaned.split(" - ", 1)
        else:
            if group is None and _looks_like_group_code(cleaned):
                group = cleaned
            else:
                free_text.append(cleaned)
            continue

        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue

        if _key_matches(key, group_keys) and group is None:
            group = value
            continue

        if _key_matches(key, teacher_keys):
            if _looks_like_group_code(value):
                if group is None:
                    group = value
                continue
            # Allow replacement if earlier "teacher" looked like a group code.
            if teacher is None or _looks_like_group_code(teacher):
                teacher = value
            continue

        if _key_matches(key, room_keys) and room is None:
            room = value

    return room, teacher, group, free_text


def _key_matches(key: str, candidates: set[str]) -> bool:
    for candidate in candidates:
        if key == candidate or key.startswith(candidate):
            return True
    return False
