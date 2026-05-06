"""
Morning Briefing Bot
Usage:
    python main.py login                        Login to ILIAS
    python main.py ingest                       Index module description PDFs
    python main.py scrape "I.BA_ITEO.F2601"     Scrape a single course
    python main.py scrape "I.BA_ITEO.F2601" --send   Scrape & send via WhatsApp
    python main.py calendar                     Show today's courses
    python main.py briefing                     Full briefing: calendar + scrape all courses
    python main.py briefing --send              Full briefing + send via WhatsApp
    python main.py whatsapp "Your message"      Send a WhatsApp message
"""

import sys
import asyncio
from datetime import date


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "login":
        from src.scraper.auth import login_interactive
        asyncio.run(login_interactive())

    elif command == "ingest":
        from src.rag.indexer import ingest_module_descriptions
        print("📚 Indexing module descriptions...\n")
        ingest_module_descriptions()

    elif command == "scrape":
        if len(sys.argv) < 3:
            print("Usage: python main.py scrape <course_identifier> [--send]")
            sys.exit(1)
        from src.scraper.course import scrape_course
        send_wa = "--send" in sys.argv
        course_id = [a for a in sys.argv[2:] if a != "--send"][0]
        result = asyncio.run(scrape_course(course_id))

        if send_wa and result.get("files"):
            from src.whatsapp import send_long
            from src.rag.agent import get_current_semester_week
            sw = get_current_semester_week()
            msg = f"📚 {course_id} — SW{sw}\n\n"
            msg += "\n".join(f"📄 {f}" for f in result["files"])
            send_long(msg)

    elif command == "calendar":
        from src.calendar import get_todays_courses
        events = get_todays_courses()
        if not events:
            print("Keine Veranstaltungen heute.")
        else:
            print(f"📅 {date.today().strftime('%d.%m.%Y')}\n")
            for e in events:
                time = f"{e['start_time']}–{e['end_time']}" if e["end_time"] else e["start_time"]
                print(f"  🕐 {time}  {e['summary']}")

    elif command == "briefing":
        asyncio.run(_run_briefing("--send" in sys.argv))

    elif command == "whatsapp":
        from src.whatsapp import send
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hallo Welt 👋"
        send(text)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


async def _run_briefing(send_wa: bool):
    """Full briefing: read calendar, scrape all courses, send via WhatsApp."""
    from src.calendar import get_todays_courses, get_todays_course_identifiers
    from src.scraper.course import scrape_course
    from src.rag.agent import get_current_semester_week

    today = date.today()
    sw = get_current_semester_week()
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    print(f"\n🌅 Briefing — {weekdays[today.weekday()]}, {today.strftime('%d.%m.%Y')} (SW{sw})")
    print("=" * 60)

    # Calendar
    print("\n📅 Lade Kalender...")
    events = get_todays_courses()
    identifiers = get_todays_course_identifiers()
    print(f"   {len(events)} Veranstaltungen, {len(identifiers)} Fächer")

    # Scrape each course
    all_results = {}
    if identifiers:
        print(f"\n📚 Scrape: {', '.join(identifiers)}")
        for course_id in identifiers:
            result = await scrape_course(course_id)
            if result.get("files"):
                all_results[course_id] = result["files"]

    # Build message
    msg_parts = [f"📅 {weekdays[today.weekday()]}, {today.strftime('%d.%m.%Y')} — SW{sw}\n"]

    for e in events:
        time = f"{e['start_time']}–{e['end_time']}" if e["end_time"] else e["start_time"]
        msg_parts.append(f"🕐 {time}  {e['course_code']}")

        if e["summary"] in all_results:
            for f in all_results[e["summary"]]:
                msg_parts.append(f"   📄 {f}")
        msg_parts.append("")

    msg = "\n".join(msg_parts).strip()

    print(f"\n{'=' * 60}")
    print(msg)
    print(f"{'=' * 60}")

    if send_wa:
        from src.whatsapp import send_long
        print("\n📤 Sende per WhatsApp...")
        send_long(msg)
    else:
        print("\n💡 Nutze --send um per WhatsApp zu senden")


if __name__ == "__main__":
    main()