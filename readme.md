# HSLU ILIAS scraper for a daily message

## Installation

```bash
pip install playwright beautifulsoup4

playwright install chromium
```

## Verwendung

### Schritt 1: Einmalig einloggen (mit 2FA)

```bash
python ilias_scraper.py login
```

- Ein Browser-Fenster öffnet sich
- Logge dich normal via SWITCHaai + 2FA ein
- Sobald du auf dem ILIAS-Dashboard bist → wechsle zum Terminal und drücke **ENTER**
- Die Session-Cookies werden in `ilias_cookies.json` gespeichert

> 💡 Die Cookies bleiben typisch 1–2 Wochen gültig. Erst wenn die Session abläuft, musst du erneut `login` ausführen.

### Schritt 2: Kursübersicht holen

```bash
python ilias_scraper.py scrape
```

Zeigt alle Kurse auf deinem Dashboard an.

### Schritt 3: Materialien eines Kurses holen

```bash
python ilias_scraper.py scrape "Analysis"
```

Navigiert in den Kurs und listet alle Materialien (Dateien, Ordner, Lernmodule etc.) auf. Das Ergebnis wird auch als JSON gespeichert.

## Troubleshooting

### "Session abgelaufen"
→ Führe erneut `python ilias_scraper.py login` aus.

### "Keine Kurse gefunden"
ILIAS ändert gelegentlich seine HTML-Struktur. Das Script speichert in diesem Fall `debug_dashboard.html` – damit kann die Parsing-Logik angepasst werden.

### Headless-Modus funktioniert nicht
Manche Shibboleth-Instanzen blockieren Headless-Browser. Falls nötig, ändere in `do_scrape()`:
```python
browser = await p.chromium.launch(headless=False)  # sichtbar statt headless
```

## Nächste Schritte (Morgen-Bot Integration)

1. **Google Calendar API** anbinden → Fächer des Tages auslesen
2. **Automatisch den richtigen Kurs scrapen** basierend auf dem Kalender
3. **Materialien an Claude API senden** → Zusammenfassung generieren
4. **Per Telegram/WhatsApp versenden**