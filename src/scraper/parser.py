from bs4 import BeautifulSoup
from dataclasses import dataclass

from src.config.settings import ILIAS_BASE_URL


@dataclass
class IliasItem:
    name: str
    url: str
    item_type: str  # "file", "folder", "unknown"


def parse_courses(html: str) -> list[IliasItem]:
    """Extract courses from the ILIAS dashboard page."""
    soup = BeautifulSoup(html, "html.parser")
    courses = []

    for link in soup.select("h4.il-item-title a"):
        href = link.get("href", "")
        name = link.get_text(strip=True)
        if name and len(name) > 2 and ("crs" in href or "ref_id" in href):
            url = _resolve_url(href)
            courses.append(IliasItem(name=name, url=url, item_type="course"))

    return courses


def parse_items(html: str) -> list[IliasItem]:
    """Extract all items (files, folders) from an ILIAS content page."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_urls = set()

    for row in soup.select(".ilCLI, .ilObjListRow"):
        item = _parse_row(row)
        if item and item.url not in seen_urls:
            seen_urls.add(item.url)
            items.append(item)

    if not items:
        for block in soup.select(".ilContainerBlock"):
            for row in block.select(".ilCLI, .ilObjListRow"):
                item = _parse_row(row)
                if item and item.url not in seen_urls:
                    seen_urls.add(item.url)
                    items.append(item)

    return items


def find_course(courses: list[IliasItem], query: str) -> IliasItem | None:
    """Find a course by (partial) name match, case-insensitive."""
    q = query.lower()
    for c in courses:
        if q in c.name.lower():
            return c
    return None


def _parse_row(el) -> IliasItem | None:
    link = (
        el.select_one("h3.il_ContainerItemTitle a")
        or el.select_one("h4.il-item-title a")
        or el.select_one("a[href*='sendfile']")
        or el.select_one("a[href*='ref_id']")
        or el.select_one("a[href*='ilias.php']")
    )
    if not link:
        return None

    name = link.get_text(strip=True)
    if not name or len(name) < 2:
        return None

    href = link.get("href", "")
    url = _resolve_url(href)
    item_type = _detect_type(el, href)

    return IliasItem(name=name, url=url, item_type=item_type)


def _detect_type(el, href: str) -> str:
    if "sendfile" in href or "ilObjFileGUI" in href:
        return "file"
    if "ilObjFolderGUI" in href or "target=fold" in href:
        return "folder"

    icon = el.select_one("img[alt]")
    if icon:
        alt = (icon.get("alt", "") or "").lower()
        if "datei" in alt or "file" in alt:
            return "file"
        if "ordner" in alt or "folder" in alt:
            return "folder"

    if "cmd=view" in href or "cmd=render" in href:
        return "folder"

    return "unknown"


def _resolve_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return ILIAS_BASE_URL + "/" + href.lstrip("/")