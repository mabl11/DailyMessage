"""
Morning Briefing Bot — MVP
Usage:
    python main.py login                        Login to ILIAS
    python main.py ingest                       Index module description PDFs
    python main.py scrape "I.BA_ITEO.F2601"     Scrape & summarize a course
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
            print("Usage: python main.py scrape <course_identifier>")
            sys.exit(1)
        from src.scraper.course import scrape_course
        asyncio.run(scrape_course(sys.argv[2]))

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()