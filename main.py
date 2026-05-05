"""
Morning Briefing Bot — MVP
Usage:
    python main.py login                        Login to ILIAS
    python main.py ingest                       Index module description PDFs
    python main.py scrape "I.BA_ITEO.F2601"     Scrape & summarize a course
    python main.py whatsapp "Your message"      Send a WhatsApp message
"""

import sys
import asyncio


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

    elif command == "whatsapp":
        from src.whatsapp import send
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hallo Welt 👋"
        send(text)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()