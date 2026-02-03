from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ParsedItem:
    date: str       # YYYY-MM-DD
    start_time: str # HH:MM
    end_time: str   # HH:MM
    subject: str
    room: Optional[str] = None
    teacher: Optional[str] = None
    ical_uid: Optional[str] = None
    ical_dtstart: Optional[str] = None


@dataclass
class ParsedSchedule:
    items: List[ParsedItem]
    warnings: List[str]
    date_from: Optional[str] = None
    date_to: Optional[str] = None
