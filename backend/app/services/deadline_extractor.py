"""Deadline, priority, and recurrence extraction for notes.

Pure regex/datetime extractor used before the LLM pipeline so all note
sources get deterministic task metadata when users include common cues.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIME = time(23, 59)
EOD_TIME = time(17, 0)
TONIGHT_TIME = time(21, 0)
NOON_TIME = time(12, 0)

TIME_TOKEN = r"(?:noon|(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?))"


class _LosAngelesFallback(tzinfo):
    """Small Windows fallback when the system IANA database is unavailable."""

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=-7 if self._is_dst(dt) else -8)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=1 if self._is_dst(dt) else 0)

    def tzname(self, dt: datetime | None) -> str:
        return "PDT" if self._is_dst(dt) else "PST"

    @staticmethod
    def _is_dst(dt: datetime | None) -> bool:
        if dt is None:
            return False
        current = dt.replace(tzinfo=None)
        start = _nth_weekday_of_month(current.year, 3, 6, 2).replace(hour=2)
        end = _nth_weekday_of_month(current.year, 11, 6, 1).replace(hour=2)
        return start <= current < end


WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> datetime:
    first = datetime(year, month, 1)
    days_until_weekday = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until_weekday + (occurrence - 1) * 7)


def _get_zone(tz: str, now: datetime) -> tzinfo:
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        if tz.upper() == "UTC":
            return timezone.utc
        if tz == "America/Los_Angeles":
            return _LosAngelesFallback()
        offset = now.utcoffset() if now.tzinfo is not None else None
        return timezone(offset, tz) if offset is not None else timezone.utc


def extract(text: str, *, now: datetime, tz: str = "UTC") -> dict | None:
    """Extract task metadata from *text*.

    Returns a dict containing any matched keys among ``due_at``, ``priority``,
    and ``recurring``. Returns ``None`` when no supported cue is present.
    """
    if not text or not text.strip():
        return None

    zone = _get_zone(tz, now)
    local_now = _as_zone(now, zone)
    result: dict[str, datetime | int | str] = {}

    due_at = _extract_due_at(text, local_now, zone)
    if due_at is not None:
        result["due_at"] = due_at

    priority = _extract_priority(text)
    if priority is not None:
        result["priority"] = priority

    recurring = _extract_recurring(text)
    if recurring is not None:
        result["recurring"] = recurring

    return result or None


def _as_zone(value: datetime, zone: tzinfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _combine(day: date, clock: time, zone: tzinfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=zone).astimezone(zone)


def _parse_time_token(value: str | None) -> time:
    if not value:
        return DEFAULT_TIME

    token = value.strip().lower()
    if token == "noon":
        return NOON_TIME

    compact = re.sub(r"\s+", "", token).replace(".", "")
    match = re.fullmatch(r"(?P<hour>1[0-2]|0?[1-9])(?::(?P<minute>[0-5]\d))?(?P<ampm>[ap]m)", compact)
    if not match:
        return DEFAULT_TIME

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm")
    if ampm == "am":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return time(hour, minute)


def _extract_due_at(text: str, now: datetime, zone: tzinfo) -> datetime | None:
    # ISO datetime before ISO date so the date part is not consumed first.
    match = re.search(
        r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return _parse_iso_datetime(match.group(0), zone)

    # "today at 3:50pm" / "at 3:50pm today" / "remind me today at 3:50pm" —
    # match the time-anchored "today" phrasing WITHOUT requiring the "by"
    # keyword. Same for tomorrow. (Fixes Round 39 — voice notes like
    # "remind me today at 3:50pm" fell through to the LLM which hallucinated
    # a date because it didn't know what "today" was.)
    match = re.search(rf"\btoday\s+(?:at\s+)?(?P<clock>{TIME_TOKEN})\b", text, re.IGNORECASE)
    if match:
        clock = _parse_time_token(match.group("clock"))
        return _combine(now.date(), clock, zone)

    match = re.search(rf"\b(?:at\s+)?(?P<clock>{TIME_TOKEN})\s+today\b", text, re.IGNORECASE)
    if match:
        clock = _parse_time_token(match.group("clock"))
        return _combine(now.date(), clock, zone)

    match = re.search(rf"\btomorrow\s+(?:at\s+)?(?P<clock>{TIME_TOKEN})\b", text, re.IGNORECASE)
    if match:
        clock = _parse_time_token(match.group("clock"))
        return _combine(now.date() + timedelta(days=1), clock, zone)

    match = re.search(rf"\b(?:at\s+)?(?P<clock>{TIME_TOKEN})\s+tomorrow\b", text, re.IGNORECASE)
    if match:
        clock = _parse_time_token(match.group("clock"))
        return _combine(now.date() + timedelta(days=1), clock, zone)

    match = re.search(rf"\bby\s+(?P<clock>{TIME_TOKEN})\s+tomorrow\b", text, re.IGNORECASE)
    if match:
        return _combine(now.date() + timedelta(days=1), _parse_time_token(match.group("clock")), zone)

    match = re.search(rf"\bby\s+tomorrow(?:\s+(?:at\s+)?(?P<clock>{TIME_TOKEN}))?\b", text, re.IGNORECASE)
    if match:
        return _combine(now.date() + timedelta(days=1), _parse_time_token(match.group("clock")), zone)

    if re.search(r"\bby\s+(?:eod|end\s+of\s+day)\b", text, re.IGNORECASE):
        return _combine(now.date(), EOD_TIME, zone)

    if re.search(r"\bby\s+tonight\b", text, re.IGNORECASE):
        return _combine(now.date(), TONIGHT_TIME, zone)

    if re.search(r"\bby\s+today\b", text, re.IGNORECASE):
        return _combine(now.date(), DEFAULT_TIME, zone)

    # Bare "today" (without a clock anchor) → end of day. Handles voice
    # transcripts like "remind me today to ..." where the user didn't say
    # an explicit time but clearly meant some time today.
    if re.search(r"\b(?:remind\s+me\s+)?today\b", text, re.IGNORECASE):
        return _combine(now.date(), DEFAULT_TIME, zone)

    match = re.search(
        rf"\bby\s+(?P<next>next\s+)?(?P<weekday>{'|'.join(WEEKDAYS)})(?:\s+(?:at\s+)?(?P<clock>{TIME_TOKEN}))?\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return _weekday_due_at(match, now, zone)

    match = re.search(r"\bin\s+(?P<count>\d+)\s+(?P<unit>hours?|days?|weeks?)\b", text, re.IGNORECASE)
    if match:
        count = int(match.group("count"))
        unit = match.group("unit").lower()
        if unit.startswith("hour"):
            return (now + timedelta(hours=count)).astimezone(zone)
        days = count * 7 if unit.startswith("week") else count
        return _combine(now.date() + timedelta(days=days), DEFAULT_TIME, zone)

    match = re.search(r"\bby\s+(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>\d{2,4}))?\b", text, re.IGNORECASE)
    if match:
        slash_due = _slash_date_due_at(match, now, zone)
        if slash_due is not None:
            return slash_due

    match = re.search(r"\b(?P<iso>\d{4}-\d{2}-\d{2})(?!T)\b", text, re.IGNORECASE)
    if match:
        try:
            parsed = date.fromisoformat(match.group("iso"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return _combine(parsed, DEFAULT_TIME, zone)

    match = re.search(rf"\bby\s+(?P<clock>{TIME_TOKEN})\b", text, re.IGNORECASE)
    if match:
        clock = _parse_time_token(match.group("clock"))
        due = _combine(now.date(), clock, zone)
        if due <= now:
            due = _combine(now.date() + timedelta(days=1), clock, zone)
        return due

    return None


def _parse_iso_datetime(value: str, zone: tzinfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _weekday_due_at(match: re.Match[str], now: datetime, zone: tzinfo) -> datetime:
    weekday_name = match.group("weekday").lower()
    target_weekday = WEEKDAYS[weekday_name]
    days_ahead = (target_weekday - now.weekday()) % 7
    if match.group("next") and days_ahead == 0:
        days_ahead = 7

    clock = _parse_time_token(match.group("clock"))
    due = _combine(now.date() + timedelta(days=days_ahead), clock, zone)

    # If the named day is today but the resolved time has passed, use next week.
    if days_ahead == 0 and due <= now:
        due = _combine(now.date() + timedelta(days=7), clock, zone)
    return due


def _slash_date_due_at(match: re.Match[str], now: datetime, zone: tzinfo) -> datetime | None:
    month = int(match.group("month"))
    day = int(match.group("day"))
    raw_year = match.group("year")
    if raw_year is None:
        year = now.year
    else:
        year = int(raw_year)
        if year < 100:
            year += 2000

    try:
        parsed = date(year, month, day)
    except ValueError:
        return None

    due = _combine(parsed, DEFAULT_TIME, zone)
    if raw_year is None and due < now:
        try:
            due = _combine(date(year + 1, month, day), DEFAULT_TIME, zone)
        except ValueError:
            return None
    return due


def _extract_priority(text: str) -> int | None:
    priority_patterns = (
        (1, r"(?<!\w)#(?:p1|high)\b"),
        (2, r"(?<!\w)#(?:p2|medium)\b"),
        (3, r"(?<!\w)#(?:p3|low)\b"),
    )
    for priority, pattern in priority_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return priority
    return None


def _extract_recurring(text: str) -> str | None:
    match = re.search(r"(?<!\w)#(?P<recurring>daily|weekly|monthly)\b", text, re.IGNORECASE)
    if match:
        return match.group("recurring").lower()
    return None
