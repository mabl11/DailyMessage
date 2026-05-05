import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
RECIPIENT = os.getenv("WHATSAPP_RECIPIENT", "")

API_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


def send(text: str, to: str | None = None) -> bool:
    """Send a WhatsApp text message. Returns True on success."""
    recipient = to or RECIPIENT

    if not all([ACCESS_TOKEN, PHONE_NUMBER_ID, recipient]):
        print("❌ WhatsApp not configured. Set WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_RECIPIENT in .env")
        return False

    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": text},
        },
        timeout=15,
    )

    if response.status_code == 200:
        msg_id = response.json().get("messages", [{}])[0].get("id", "?")
        print(f"✅ WhatsApp sent (ID: {msg_id})")
        return True

    error = response.json().get("error", {}).get("message", response.text)
    print(f"❌ WhatsApp error {response.status_code}: {error}")
    return False


def send_long(text: str, to: str | None = None) -> bool:
    """Send a long message, splitting at 4000 chars if needed."""
    if len(text) <= 4000:
        return send(text, to)

    mid = text.rfind("\n", 0, 4000)
    if mid == -1:
        mid = 4000
    return send(text[:mid], to) and send(text[mid:], to)


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hallo Welt 👋"
    send(text)
