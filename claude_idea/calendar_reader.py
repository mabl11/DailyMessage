"""
HSLU Kalender-Integration – Morgen-Briefing Bot
=================================================
Liest einen ICS/iCal-Feed und extrahiert die Fächer des heutigen Tages.

Voraussetzungen:
  pip install icalendar requests python-dotenv

Verwendung:
  1. Kopiere deine Kalender-URL in die .env Datei:
     HSLU_CALENDAR_URL=https://example.hslu.ch/calendar/feed.ics

  2. python calendar_reader.py              → Zeigt heutige Fächer
     python calendar_reader.py tomorrow     → Zeigt morgige Fächer
     python calendar_reader.py 2026-05-10   → Zeigt Fächer an einem bestimmten Datum
"""

import sys
import os
import re
import requests
from datetime import datetime, date, timedelta
from pathlib import Path
from icalendar import Calendar
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
CALENDAR_URL = os.getenv("HSLU_CALENDAR_URL", "")
CACHE_FILE = Path("calendar_cache.ics")
CACHE_MAX_AGE_HOURS = 6  # Cache erneuern nach X Stunden


def fetch_calendar() -> Calendar:
    """
    Holt den ICS-Feed. Nutzt einen lokalen Cache um nicht bei jedem
    Aufruf die HSLU-Server zu belasten.
    """
    if not CALENDAR_URL:
        print("❌ Keine Kalender-URL konfiguriert!")
        print("   Erstelle eine .env Datei mit:")
        print("   HSLU_CALENDAR_URL=https://deine-kalender-url.ics")
        sys.exit(1)

    # Cache prüfen
    if CACHE_FILE.exists():
        age_hours = (
            datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
        ) / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            print(f"📦 Verwende Cache ({age_hours:.1f}h alt)")
            return Calendar.from_ical(CACHE_FILE.read_bytes())

    # Frisch fetchen
    print(f"📡 Lade Kalender-Feed...")
    try:
        resp = requests.get(CALENDAR_URL, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Fehler beim Laden des Kalenders: {e}")
        if CACHE_FILE.exists():
            print("   Verwende alten Cache als Fallback.")
            return Calendar.from_ical(CACHE_FILE.read_bytes())
        sys.exit(1)

    # Cache speichern
    CACHE_FILE.write_bytes(resp.content)
    print(f"✅ Kalender geladen & gecacht.")

    return Calendar.from_ical(resp.content)


def get_events_for_date(cal: Calendar, target_date: date) -> list[dict]:
    """
    Extrahiert alle Events eines bestimmten Tages aus dem Kalender.
    """
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        if not dtstart:
            continue

        dt = dtstart.dt

        # Ganztägige Events (date) vs. zeitbasierte Events (datetime)
        if isinstance(dt, datetime):
            event_date = dt.date()
        elif isinstance(dt, date):
            event_date = dt
        else:
            continue

        if event_date != target_date:
            continue

        # Event-Daten extrahieren
        summary = str(component.get("SUMMARY", "Ohne Titel"))
        location = str(component.get("LOCATION", ""))
        description = str(component.get("DESCRIPTION", ""))

        # Start- und Endzeit
        dtend = component.get("DTEND")
        start_time = dt.strftime("%H:%M") if isinstance(dt, datetime) else "ganztägig"
        end_time = ""
        if dtend and isinstance(dtend.dt, datetime):
            end_time = dtend.dt.strftime("%H:%M")

        # Fachkürzel extrahieren (z.B. "ANLIS" aus "ANLIS.H2401 - Analysis")
        course_code = extract_course_code(summary)

        events.append({
            "summary": summary,
            "course_code": course_code,
            "location": location,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "raw_summary": summary,
        })

    # Nach Startzeit sortieren
    events.sort(key=lambda e: e["start_time"])
    return events


def extract_course_code(summary: str) -> str:
    """
    Versucht ein Modulkürzel aus dem Event-Titel zu extrahieren.
    Typische HSLU-Formate:
      - "I.BA_ITEO.F2601"          → ITEO
      - "I.BA_ANAF_K.F2602"        → ANAF
      - "ANLIS.H2401 - Analysis"   → ANLIS
      - "DMATH - Diskrete Mathe"   → DMATH
    """
    # Muster 1: HSLU Format "I.BA_KÜRZEL.Fxxxx" oder "I.BA_KÜRZEL_X.Fxxxx"
    match = re.search(r"I\.BA_([A-Z]{2,10})(?:_[A-Z])?\.F\d+", summary)
    if match:
        return match.group(1)

    # Muster 2: "KÜRZEL.Semester" (z.B. ANLIS.H2401)
    match = re.match(r"^([A-Z]{2,10})\.\w+", summary)
    if match:
        return match.group(1)

    # Muster 3: "KÜRZEL - Beschreibung"
    match = re.match(r"^([A-Z]{2,10})\s*[-–]", summary)
    if match:
        return match.group(1)

    # Muster 4: Kürzel in Klammern
    match = re.search(r"\(([A-Z]{2,10})\)", summary)
    if match:
        return match.group(1)

    # Fallback
    return summary.split(" ")[0].split(".")[0].split("-")[0].strip()


def get_unique_courses(events: list[dict]) -> list[str]:
    """Gibt eine Liste einzigartiger Fachkürzel zurück."""
    seen = set()
    codes = []
    for e in events:
        code = e["course_code"]
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def format_day_overview(events: list[dict], target_date: date) -> str:
    """Formatiert eine hübsche Tagesübersicht."""
    weekdays_de = [
        "Montag", "Dienstag", "Mittwoch", "Donnerstag",
        "Freitag", "Samstag", "Sonntag",
    ]
    day_name = weekdays_de[target_date.weekday()]
    header = f"📅 {day_name}, {target_date.strftime('%d.%m.%Y')}"

    if not events:
        return f"{header}\n\n😴 Keine Veranstaltungen heute."

    lines = [header, ""]
    for e in events:
        time_str = e["start_time"]
        if e["end_time"]:
            time_str += f"–{e['end_time']}"

        lines.append(f"  🕐 {time_str}  {e['summary']}")
        if e["location"]:
            lines.append(f"     📍 {e['location']}")

    # Einzigartige Fächer
    courses = get_unique_courses(events)
    if courses:
        lines.append("")
        lines.append(f"📚 Fächer heute: {', '.join(courses)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API – für Integration mit dem Morgen-Bot
# ---------------------------------------------------------------------------
def get_todays_courses() -> list[dict]:
    """
    Gibt die heutigen Events zurück.
    Für die Integration mit dem ILIAS-Scraper und dem Briefing-Bot.
    """
    cal = fetch_calendar()
    return get_events_for_date(cal, date.today())


def get_todays_course_codes() -> list[str]:
    """Gibt nur die Fachkürzel des heutigen Tages zurück."""
    events = get_todays_courses()
    return get_unique_courses(events)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    target = date.today()

    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "tomorrow":
            target = date.today() + timedelta(days=1)
        elif arg == "week":
            # Ganze Woche anzeigen
            cal = fetch_calendar()
            for i in range(7):
                d = date.today() + timedelta(days=i)
                events = get_events_for_date(cal, d)
                print(format_day_overview(events, d))
                print()
            return
        else:
            try:
                target = datetime.strptime(arg, "%Y-%m-%d").date()
            except ValueError:
                print(f"❌ Ungültiges Datum: {arg}")
                print("   Verwende: YYYY-MM-DD, 'tomorrow', oder 'week'")
                sys.exit(1)

    cal = fetch_calendar()
    events = get_events_for_date(cal, target)
    print(format_day_overview(events, target))

    # Fachkürzel für Integration ausgeben
    courses = get_unique_courses(events)
    if courses:
        print(f"\n🔗 Diese Kürzel können für den ILIAS-Scraper verwendet werden:")
        for c in courses:
            print(f"   python ilias_scraper.py scrape \"{c}\"")


if __name__ == "__main__":
    main()
