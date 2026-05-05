"""
Morgen-Briefing Bot – Hauptscript
===================================
Voraussetzungen:
  pip install yfinance perigon python-dotenv icalendar requests playwright beautifulsoup4 anthropic pymupdf
  playwright install chromium

Verwendung:
  python briefing_bot.py              → Volles Briefing & WhatsApp senden
  python briefing_bot.py --no-send    → Nur im Terminal anzeigen
  python briefing_bot.py --no-ilias   → Ohne ILIAS
"""

import sys
import os
import json
import asyncio
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from calendar_reader import fetch_calendar, get_events_for_date, get_unique_courses
from market_news import get_market_data, get_news, format_market_data, format_news
from whatsapp_sender import send_message
from ilias_scraper import (
    COOKIES_FILE, ILIAS_DASHBOARD_URL, PAGE_TIMEOUT,
    extract_courses, find_course, scrape_course_deep, get_current_week_number,
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRIEFING_LOG_DIR = Path("briefing_logs")
BRIEFING_LOG_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# 1. ILIAS: Kurse scrapen + PDFs extrahieren
# ---------------------------------------------------------------------------
async def scrape_todays_courses(course_codes: list[str]) -> dict[str, dict]:
    """Für jedes heutige Fach: in ILIAS navigieren, PDFs finden & Text extrahieren."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    if not COOKIES_FILE.exists():
        print("⚠️  Keine ILIAS-Cookies.")
        return {}

    cookies = json.loads(COOKIES_FILE.read_text())
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        await context.add_cookies(cookies)
        page = await context.new_page()

        print("📡 Lade ILIAS Dashboard...")
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)

        if "login" in page.url.lower() or "shibboleth" in page.url.lower():
            print("❌ ILIAS-Session abgelaufen! → python ilias_scraper.py login")
            await browser.close()
            return {}

        # Warten bis Inhalte geladen sind
        await page.wait_for_timeout(5000)
        try:
            await page.wait_for_selector(".ilCLI, .ilObjListRow, .il-item", timeout=10000)
        except Exception:
            pass

        soup = BeautifulSoup(await page.content(), "html.parser")
        all_courses = extract_courses(soup)

        if not all_courses:
            print("⚠️  Keine Kurse auf ILIAS gefunden.")
            await browser.close()
            return {}

        print(f"📚 {len(all_courses)} Kurse auf ILIAS")

        for code in course_codes:
            target = find_course(all_courses, code)
            if not target:
                print(f"  ⚠️  '{code}' nicht gefunden.")
                continue

            print(f"\n  🔍 {code}: '{target['name']}'")
            result = await scrape_course_deep(page, target["url"], code)

            results[code] = result
            pdf_count = len(result["pdfs"])
            total_chars = sum(len(p["text"] or "") for p in result["pdfs"])
            print(f"  ✅ {code}: {pdf_count} PDFs, {total_chars} Zeichen extrahiert")

        await browser.close()

    return results


# ---------------------------------------------------------------------------
# 2. LLM Briefing
# ---------------------------------------------------------------------------
def generate_briefing(market_data, news, events, course_data, target_date) -> str:
    if ANTHROPIC_API_KEY:
        return _llm_briefing(market_data, news, events, course_data, target_date)
    return _template_briefing(market_data, news, events, course_data, target_date)


def _llm_briefing(market_data, news, events, course_data, target_date) -> str:
    import anthropic

    ctx = []
    ctx.append("=== MARKTDATEN ===")
    ctx.append(format_market_data(market_data))

    ctx.append("\n=== NEWS ===")
    for a in news:
        ctx.append(f"- [{a['category']}] {a['title']} ({a.get('source', '')})")
        if a.get("summary"):
            ctx.append(f"  {a['summary'][:200]}")

    ctx.append("\n=== HEUTIGE FÄCHER ===")
    for e in events:
        code = e["course_code"]
        time_str = f"{e['start_time']}–{e['end_time']}" if e["end_time"] else e["start_time"]
        ctx.append(f"\n--- {code} ({time_str}) ---")

        if code in course_data and course_data[code]["pdfs"]:
            for pdf in course_data[code]["pdfs"]:
                ctx.append(f"\n[PDF: {pdf['name']}]")
                # Max 3000 Zeichen pro PDF im Prompt
                ctx.append(pdf["text"][:3000] if pdf["text"] else "(kein Text)")
        else:
            ctx.append("(Keine Materialien gefunden)")

    context = "\n".join(ctx)
    sw = get_current_week_number()
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    day_name = weekdays[target_date.weekday()]

    prompt = f"""Du bist mein persönlicher Morgen-Briefing-Assistent. Erstelle ein WhatsApp-Briefing für {day_name}, {target_date.strftime('%d.%m.%Y')} (Semesterwoche {sw}).

Rohdaten:

{context}

Regeln:
1. Kurze Begrüssung + Datum
2. 📊 MÄRKTE: Gold, Öl mit Preisen und Tagesveränderung. 2-3 Zeilen max.
3. 📰 NEWS: Top 3-5 Schlagzeilen. Finanzen etwas ausführlicher, Politik nur 1-2 Sätze.
4. 📚 STUDIUM – DAS IST DER WICHTIGSTE TEIL:
   Für jedes heutige Fach:
   - Fachkürzel und Uhrzeit
   - Basierend auf den PDF-Inhalten: Was sind die Hauptthemen? 
   - Fasse den Stoff so zusammen, dass ich in 30 Sekunden weiss worum es geht.
   - Nenne konkrete Konzepte, Formeln, Methoden die behandelt werden.
   - 3-5 Sätze pro Fach.
5. Max 2000 Zeichen. Emojis als Gliederung.
6. Deutsch, informell (du-Form).
7. Keine Links/URLs.

Briefing:"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _template_briefing(market_data, news, events, course_data, target_date) -> str:
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    sw = get_current_week_number()
    parts = [f"☀️ Guten Morgen! {weekdays[target_date.weekday()]}, {target_date.strftime('%d.%m.%Y')} (SW{sw})", ""]
    parts.append(format_market_data(market_data))
    parts.append("")
    parts.append(format_news(news))
    parts.append("")

    if events:
        parts.append("📚 Dein Tag:")
        for e in events:
            code = e["course_code"]
            time_str = f"{e['start_time']}–{e['end_time']}" if e["end_time"] else e["start_time"]
            parts.append(f"\n  🕐 {time_str}  {code}")
            if code in course_data and course_data[code]["pdfs"]:
                for pdf in course_data[code]["pdfs"]:
                    parts.append(f"     📄 {pdf['name']}")
                    if pdf["text"]:
                        preview = pdf["text"][:300].replace("\n", " ")
                        parts.append(f"     → {preview}...")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 3. Hauptfunktion
# ---------------------------------------------------------------------------
async def run_briefing(send_whatsapp: bool = True, use_ilias: bool = True):
    today = date.today()
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    print("=" * 60)
    print(f"🌅 Morgen-Briefing – {weekdays[today.weekday()]}, {today.strftime('%d.%m.%Y')}")
    print("=" * 60)

    print("\n📅 Lade Kalender...")
    cal = fetch_calendar()
    events = get_events_for_date(cal, today)
    course_codes = get_unique_courses(events)
    print(f"   {len(events)} Veranstaltungen, Fächer: {', '.join(course_codes) or 'keine'}")

    print("\n📊 Lade Marktdaten...")
    market_data = get_market_data()

    print("\n📰 Lade News...")
    news = get_news()

    course_data = {}
    if use_ilias and course_codes:
        print(f"\n📚 ILIAS: Lade Materialien für {', '.join(course_codes)}...")
        course_data = await scrape_todays_courses(course_codes)
    elif not course_codes:
        print("\n📚 Keine Fächer heute.")

    print("\n✍️  Generiere Briefing...")
    briefing = generate_briefing(market_data, news, events, course_data, today)

    print("\n" + "=" * 60)
    print("📱 BRIEFING:")
    print("=" * 60)
    print(briefing)
    print("=" * 60)

    log_file = BRIEFING_LOG_DIR / f"briefing_{today.isoformat()}.txt"
    log_file.write_text(briefing, encoding="utf-8")

    if send_whatsapp:
        print("\n📤 Sende per WhatsApp...")
        if len(briefing) > 4000:
            mid = briefing.rfind("\n", 0, 4000)
            send_message(briefing[:mid])
            send_message(briefing[mid:])
        else:
            send_message(briefing)
    else:
        print("\n⏭️  WhatsApp übersprungen (--no-send)")

    return briefing


def main():
    send = "--no-send" not in sys.argv
    ilias = "--no-ilias" not in sys.argv
    asyncio.run(run_briefing(send_whatsapp=send, use_ilias=ilias))


if __name__ == "__main__":
    main()
