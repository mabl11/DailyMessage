import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODULE_DESCRIPTIONS_DIR = DATA_DIR / "module_descriptions"
CACHE_DIR = BASE_DIR / "cache"
PDF_CACHE_DIR = CACHE_DIR / "pdfs"
CHROMA_DIR = CACHE_DIR / "chroma"
COOKIES_FILE = CACHE_DIR / "ilias_cookies.json"

for d in [DATA_DIR, MODULE_DESCRIPTIONS_DIR, CACHE_DIR, PDF_CACHE_DIR, CHROMA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ILIAS_BASE_URL = "https://elearning.hslu.ch"
ILIAS_DASHBOARD_URL = (
    f"{ILIAS_BASE_URL}/ilias/ilias.php"
    "?baseClass=ilDashboardGUI&cmd=jumpToSelectedItems"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

PAGE_TIMEOUT = 30_000
MAX_PDF_PAGES = 20
MAX_TEXT_PER_PDF = 8000