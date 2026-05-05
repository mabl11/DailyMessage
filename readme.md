# Morning Briefing Bot

Daily WhatsApp briefing with market data, news, and HSLU lecture summaries.

## MVP: ILIAS Course Scraper

Intelligent scraper that navigates HSLU ILIAS, finds current lecture materials using RAG, and provides a summary.

### Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Add your Groq API key (free: console.groq.com)
```

### Usage

```bash
# 1. Login to ILIAS (once, repeat when session expires)
python main.py login

# 2. Index module descriptions for RAG (once per semester)
#    Place PDFs in data/module_descriptions/ first
python main.py ingest

# 3. Scrape & summarize a course example
python main.py scrape "I.BA_ITEO.F2601"
```

### Project Structure - Folder SW

```
morning-briefing/
├── main.py                         Entry point
├── src/
│   ├── config/
│   │   └── settings.py             All configuration
│   ├── scraper/
│   │   ├── auth.py                 ILIAS login (Playwright + cookies)
│   │   ├── parser.py               HTML parsing for ILIAS pages
│   │   ├── navigator.py            Page navigation & PDF downloads
│   │   └── course.py               Main orchestrator
│   └── rag/
│       ├── llm.py                  Groq/Llama client
│       ├── indexer.py              PDF → ChromaDB vector store
│       └── agent.py                Intelligent folder selection
├── data/
│   └── module_descriptions/        Place module PDFs here
├── cache/                          Auto-generated caches
├── requirements.txt
└── .env
```

### How the RAG works

1. Place module description PDFs in `data/module_descriptions/`
2. Run `python main.py ingest` — chunks and embeds them into ChromaDB
3. When scraping, the agent queries the vector store for "what's in SW12?" context
4. This context helps the LLM pick the right folder, even without SW labels

### Roadmap

- [x] MVP: ILIAS scraper with RAG-based navigation
- [ ] WhatsApp integration (Meta Cloud API)
- [ ] Calendar integration (ICS feed)
- [ ] News integration (Perigon API)
- [ ] Finance data (yfinance)
- [ ] Automated daily briefing (cron)