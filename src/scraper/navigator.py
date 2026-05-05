from playwright.async_api import Page

from src.config.settings import PAGE_TIMEOUT
from src.scraper.parser import IliasItem
from src.scraper.pdf_extractor import (
    extract_text, get_cached_text, save_cached_text, pdf_cache_path
)


async def navigate_and_get_html(page: Page, url: str) -> str:
    """Navigate to a URL and return the page HTML after content loads."""
    await page.goto(url, timeout=PAGE_TIMEOUT)
    await page.wait_for_timeout(3000)
    try:
        await page.wait_for_selector(
            ".ilCLI, .ilObjListRow, .il-item, h4.il-item-title",
            timeout=7000,
        )
    except Exception:
        pass
    return await page.content()


async def download_pdf(page: Page, item: IliasItem, course_code: str) -> str | None:
    """Download a file from ILIAS and extract its text. Uses cache when available."""
    cached = get_cached_text(course_code, item.name)
    if cached:
        print(f"    📦 cached: {item.name}")
        return cached

    cache_path = pdf_cache_path(course_code, item.name)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists() and cache_path.stat().st_size > 0:
        text = extract_text(cache_path)
        if text:
            save_cached_text(course_code, item.name, text)
        return text

    print(f"    📥 downloading: {item.name}...")
    try:
        async with page.expect_download(timeout=15000) as dl_info:
            await page.goto(item.url, timeout=PAGE_TIMEOUT)
        download = await dl_info.value
        await download.save_as(str(cache_path))
    except Exception:
        try:
            resp = await page.goto(item.url, timeout=PAGE_TIMEOUT)
            if resp:
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct or "octet" in ct:
                    cache_path.write_bytes(await resp.body())
                else:
                    print(f"    ⚠️  not a PDF: {item.name}")
                    return None
        except Exception as e:
            print(f"    ❌ download failed: {item.name} — {e}")
            return None

    text = extract_text(cache_path)
    if text:
        save_cached_text(course_code, item.name, text)
        print(f"    ✅ extracted {len(text)} chars")
    return text