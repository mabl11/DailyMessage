"""
WhatsApp Sender – Morgen-Briefing Bot
======================================
Sendet Nachrichten via Meta WhatsApp Cloud API.

Voraussetzungen:
  pip install requests python-dotenv

Setup:
  1. App erstellen auf developers.facebook.com
  2. WhatsApp Product hinzufügen
  3. Access Token & Phone Number ID in .env eintragen

Verwendung:
  python whatsapp_sender.py                    → Sendet "Hallo Welt" Testnachricht
  python whatsapp_sender.py "Deine Nachricht"  → Sendet beliebige Nachricht
"""

import sys
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
RECIPIENT_NUMBER = os.getenv("WHATSAPP_RECIPIENT", "")  # Deine Nummer, z.B. 41791234567

API_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


# ---------------------------------------------------------------------------
# Nachricht senden
# ---------------------------------------------------------------------------
def send_message(text: str, to: str | None = None) -> bool:
    """
    Sendet eine WhatsApp-Textnachricht.
    Gibt True bei Erfolg zurück, False bei Fehler.
    """
    recipient = to or RECIPIENT_NUMBER

    if not ACCESS_TOKEN:
        print("❌ WHATSAPP_ACCESS_TOKEN fehlt in .env!")
        return False
    if not PHONE_NUMBER_ID:
        print("❌ WHATSAPP_PHONE_NUMBER_ID fehlt in .env!")
        return False
    if not recipient:
        print("❌ WHATSAPP_RECIPIENT fehlt in .env!")
        return False

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": text},
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=15)

        if resp.status_code == 200:
            msg_id = resp.json().get("messages", [{}])[0].get("id", "?")
            print(f"✅ Nachricht gesendet! (ID: {msg_id})")
            return True
        else:
            error = resp.json().get("error", {})
            print(f"❌ Fehler {resp.status_code}: {error.get('message', resp.text)}")
            return False

    except Exception as e:
        print(f"❌ Verbindungsfehler: {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hallo Welt 👋"
    send_message(text)


if __name__ == "__main__":
    main()
