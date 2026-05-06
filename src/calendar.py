import os
import re
import requests
from datetime import datetime, date, timedelta
from pathlib import Path
from icalendar import Calendar

from dotenv import load_dotenv
load_dotenv()

CALENDAR_URL = os.getenv("HSLU_CALENDAR_URL", "")
CACHE_FILE = Path("cache/calendar.ics")
CACHE_MAX_AGE_HOURS = 6


def fetch_calendar() -> Calendar:
    """Fetch ICS feed, using a local cache to avoid excessive requests."""
    if not CALENDAR_URL:
        raise ValueError("HSLU_CALENDAR_URL not set in .env")

    if CACHE_FILE.exists():
        age = (datetime.now().timestamp() - CACHE_FILE.stat().st_mtime) / 3600
        if age < CACHE_MAX_AGE_HOURS:
            return Calendar.from_ical(CACHE_FILE.read_bytes())

    resp = requests.get(CALENDAR_URL, timeout=15)
    resp.raise_for_status()
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_bytes(resp.content)
    return Calendar.from_ical(resp.content)


def get_todays_courses() -> list[dict]:
    """Return today's calendar events with course codes extracted."""
    cal = fetch_calendar()
    today = date.today()
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        if not dtstart:
            continue

        dt = dtstart.dt
        if isinstance(dt, datetime):
            event_date = _to_local(dt).date()
        elif isinstance(dt, date):
            event_date = dt
        else:
            continue
        if event_date != today:
            continue

        summary = str(component.get("SUMMARY", ""))
        location = str(component.get("LOCATION", ""))
        dtend = component.get("DTEND")

        start_time = _to_local(dt).strftime("%H:%M") if isinstance(dt, datetime) else "ganztägig"
        end_dt = dtend.dt if dtend else None
        end_time = _to_local(end_dt).strftime("%H:%M") if end_dt and isinstance(end_dt, datetime) else ""

        events.append({
            "summary": summary,
            "course_code": _extract_code(summary),
            "location": location,
            "start_time": start_time,
            "end_time": end_time,
        })

    events.sort(key=lambda e: e["start_time"])
    return events


def get_todays_course_identifiers() -> list[str]:
    """Return unique course identifiers (e.g. 'I.BA_ITEO.F2601') for today."""
    events = get_todays_courses()
    seen = set()
    identifiers = []
    for e in events:
        s = e["summary"]
        if s not in seen and e["course_code"]:
            seen.add(s)
            identifiers.append(s)
    return identifiers


def _extract_code(summary: str) -> str:
    """Extract short course code. 'I.BA_ITEO.F2601' -> 'ITEO'"""
    match = re.search(r"I\.BA_([A-Z]{2,10})(?:_[A-Z])?[\._]", summary)
    return match.group(1) if match else ""


def _to_local(dt: datetime) -> datetime:
    """Convert a datetime to local (Europe/Zurich) timezone."""
    from zoneinfo import ZoneInfo
    local_tz = ZoneInfo("Europe/Zurich")
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(local_tz)


if __name__ == "__main__":
    events = get_todays_courses()
    if not events:
        print("Keine Veranstaltungen heute.")
    else:
        for e in events:
            time = f"{e['start_time']}–{e['end_time']}" if e["end_time"] else e["start_time"]
            print(f"  🕐 {time}  {e['summary']}")