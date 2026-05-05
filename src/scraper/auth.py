import json
import asyncio
from playwright.async_api import async_playwright, BrowserContext

from src.config.settings import COOKIES_FILE, ILIAS_DASHBOARD_URL, PAGE_TIMEOUT


async def login_interactive():
    """Open browser for manual SWITCHaai + 2FA login. Saves session cookies."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(ILIAS_DASHBOARD_URL, timeout=PAGE_TIMEOUT)

        input("\n>>> Press ENTER after you've logged in... ")

        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"✅ {len(cookies)} cookies saved to {COOKIES_FILE}")

        await browser.close()


async def create_authenticated_context(playwright) -> BrowserContext:
    """Create a browser context with saved session cookies."""
    if not COOKIES_FILE.exists():
        raise FileNotFoundError(
            "No cookies found. Run 'python -m src.scraper.auth' first."
        )

    cookies = json.loads(COOKIES_FILE.read_text())
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(accept_downloads=True)
    await context.add_cookies(cookies)
    return context


async def verify_session(page) -> bool:
    """Check if the current session is still valid."""
    url = page.url.lower()
    return "login" not in url and "shibboleth" not in url


if __name__ == "__main__":
    print("=" * 50)
    print("ILIAS Login — Manual Mode")
    print("=" * 50)
    print("A browser window will open.")
    print("Log in via SWITCHaai + 2FA, then press ENTER.\n")
    asyncio.run(login_interactive())