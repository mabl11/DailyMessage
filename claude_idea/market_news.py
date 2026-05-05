"""
Marktdaten & News – Morgen-Briefing Bot
========================================
Holt Ölpreis, Goldpreis und Top-News für das tägliche Briefing.

Voraussetzungen:
  pip install yfinance perigon python-dotenv

Verwendung:
  python market_news.py              → Alles anzeigen
  python market_news.py market       → Nur Marktdaten
  python market_news.py news         → Nur News
  python market_news.py json         → Alles als JSON
"""

import sys
import os
import json
from datetime import datetime, timedelta

import yfinance as yf
from perigon import V1Api, ApiClient
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PERIGON_API_KEY = os.getenv("PERIGON_API_KEY", "")

TICKERS = {
    "gold":  {"symbol": "GC=F",  "name": "Gold",      "unit": "USD/oz"},
    "wti":   {"symbol": "CL=F",  "name": "WTI Öl",    "unit": "USD/barrel"},
    "brent": {"symbol": "BZ=F",  "name": "Brent Öl",  "unit": "USD/barrel"},
}


# ---------------------------------------------------------------------------
# 1. Marktdaten (Öl & Gold)
# ---------------------------------------------------------------------------
def get_market_data() -> dict:
    """Holt aktuelle Öl- und Goldpreise via yfinance."""
    results = {}

    for key, info in TICKERS.items():
        try:
            hist = yf.Ticker(info["symbol"]).history(period="2d")

            if len(hist) >= 2:
                price, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
                change = price - prev
                change_pct = (change / prev) * 100
            elif len(hist) == 1:
                price, change, change_pct = hist["Close"].iloc[-1], 0.0, 0.0
            else:
                results[key] = {**info, "price": None, "change": 0, "change_pct": 0, "timestamp": None}
                continue

            results[key] = {
                **info,
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "timestamp": hist.index[-1].strftime("%d.%m.%Y %H:%M"),
            }
        except Exception as e:
            print(f"⚠️  Fehler bei {info['name']}: {e}")
            results[key] = {**info, "price": None, "change": 0, "change_pct": 0, "timestamp": None, "error": str(e)}

    return results


def format_market_data(data: dict) -> str:
    """Formatiert Marktdaten für das Briefing."""
    timestamps = [v["timestamp"] for v in data.values() if v.get("timestamp")]
    ts_str = f" (Stand: {timestamps[0]})" if timestamps else ""

    lines = [f"📊 Marktdaten{ts_str}", ""]
    for info in data.values():
        if info["price"] is None:
            lines.append(f"  {info['name']}: ❌ Nicht verfügbar")
            continue

        arrow = "🟢 ▲" if info["change_pct"] > 0 else "🔴 ▼" if info["change_pct"] < 0 else "⚪ ─"
        sign = "+" if info["change"] >= 0 else ""
        lines.append(
            f"  {info['name']}: ${info['price']:.2f} {info['unit']}  "
            f"{arrow} {sign}{info['change']:.2f} ({sign}{info['change_pct']:.2f}%)"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. News via Perigon SDK
# ---------------------------------------------------------------------------
def _get_perigon_client() -> V1Api:
    """Erstellt einen Perigon API Client."""
    if not PERIGON_API_KEY:
        raise ValueError("Kein PERIGON_API_KEY in .env gesetzt!")
    return V1Api(ApiClient(api_key=PERIGON_API_KEY))


def get_news(max_finance: int = 5, max_politics: int = 3) -> list[dict]:
    """
    Holt Top-News via Perigon SDK.
    Zwei Abfragen: Wirtschaft/Finanzen + Politik.
    """
    try:
        api = _get_perigon_client()
    except ValueError as e:
        print(f"⚠️  {e}")
        return []

    since = (datetime.now() - timedelta(hours=24)).isoformat()
    articles = []

    articles.extend(_fetch_articles(api, category="Business,Finance,Economics", label="Finanzen", size=max_finance, since=since))
    articles.extend(_fetch_articles(api, category="Politics", label="Politik", size=max_politics, since=since))

    return _deduplicate(articles)


def _fetch_articles(api: V1Api, category: str, label: str, size: int, since: str) -> list[dict]:
    """Einzelne Perigon-Abfrage via SDK."""
    try:
        result = api.search_articles(
            category=category,
            var_from=since,
            sort_by="date",
            size=size,
            language="en",
            show_reprints=False,
        )

        return [
            {
                "title": a.title or "Ohne Titel",
                "link": a.url or "",
                "published": a.pub_date or "",
                "category": label,
                "source": a.source.domain if a.source else "",
                "summary": a.summary or "",
            }
            for a in (result.articles or [])
        ]
    except Exception as e:
        print(f"⚠️  Perigon-Fehler ({label}): {e}")
        return []


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Entfernt doppelte Artikel basierend auf Titel."""
    seen = set()
    unique = []
    for a in articles:
        key = a["title"].lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def format_news(articles: list[dict]) -> str:
    """Formatiert News für das Briefing, gruppiert nach Kategorie."""
    if not articles:
        return "📰 News\n\n  Keine aktuellen News gefunden."

    lines = ["📰 Top-News", ""]

    for emoji, label in [("💰", "Finanzen"), ("🏛️", "Politik")]:
        group = [a for a in articles if a["category"] == label]
        if not group:
            continue
        category_name = "Wirtschaft & Finanzen" if label == "Finanzen" else "Politik"
        lines.append(f"  {emoji} {category_name}:")
        for i, a in enumerate(group, 1):
            source = f" ({a['source']})" if a.get("source") else ""
            lines.append(f"    {i}. {a['title']}{source}")
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Public API – für Integration mit dem Morgen-Bot
# ---------------------------------------------------------------------------
def get_briefing_data() -> dict:
    """Holt alle Markt- und Newsdaten für das Briefing."""
    print("📊 Lade Marktdaten...")
    market = get_market_data()
    print("📰 Lade News...")
    news = get_news()
    return {"market": market, "news": news, "timestamp": datetime.now().isoformat()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if mode in ("all", "market"):
        print(format_market_data(get_market_data()))
        print()

    if mode in ("all", "news"):
        print(format_news(get_news()))
        print()

    if mode == "json":
        print(json.dumps(get_briefing_data(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
