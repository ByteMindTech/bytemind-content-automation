# Blog Article Publishing Demo

Complete demonstration of the ByteMind Content Automation publishing lifecycle.

## Quick Start

```bash
# 1. Ensure .env is configured
cp .env.example .env  # Edit with your Gemini API key

# 2. Start the stack
docker compose -f docker-compose.dev.yml up -d

# 3. Run the demo
./scripts/demo/run_demo.sh
```

## What the Demo Does

```
┌──────────────────────┐
│  sample-article.md   │  ← Real blog post (Markdown + YAML frontmatter)
└──────────┬───────────┘
           │ POST /generate
┌──────────▼───────────┐
│   Content Service    │  ← Parses frontmatter, stores in PostgreSQL
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│   Gemini AI Engine   │  ← Generates SEO, LinkedIn, Medium, social
└──────────┬───────────┘
           │ POST /publish
┌──────────▼───────────┐
│  Publishing Service  │  ← Website record + Medium bundle + LinkedIn draft
└──────────┬───────────┘
           │
    ┌──────┼──────────┐
    │      │          │
    ▼      ▼          ▼
 Website  Medium    LinkedIn
 (DB)    (bundle)   (draft)
```

## API Calls Made

| Step | Method | Endpoint | Description |
|------|--------|----------|-------------|
| 1 | GET | `/health` | Verify API is running |
| 2 | POST | `/generate` | Ingest article + AI enrichment |
| 3 | GET | `/articles` | Verify article in database |
| 4 | POST | `/publish` | Publish to website + generate bundles |
| 5 | GET | `/analytics` | Show platform metrics |

## Sample Article

The demo uses `sample-article.md` — a real technical blog post about building self-healing data pipelines with DuckDB and Python. It includes:

- Full YAML frontmatter (title, slug, date, tags, author, excerpt)
- Code blocks (Python, SQL)
- Architecture diagrams (ASCII)
- Tables and structured content
- ~1,800 words (~12 min read)

## Running Against Remote VPS

```bash
API_BASE=http://51.255.193.54:8000 ./scripts/demo/run_demo.sh --api-only
```

## Running Without Docker (dev mode)

```bash
# Terminal 1: Start PostgreSQL (if not via Docker)
docker run -d --name pg -e POSTGRES_DB=bytemind_content -e POSTGRES_USER=bytemind -e POSTGRES_PASSWORD=devpass -p 5432:5432 postgres:16-alpine

# Terminal 2: Run the API
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Terminal 3: Run demo
./scripts/demo/run_demo.sh --api-only
```

## Expected Output

```
[DEMO] Checking API health...
  ✓ API is running at http://localhost:8000
[DEMO] Ingesting sample article: sample-article.md
  ✓ Article ingested & enriched
     ID:        a1b2c3d4-e5f6-...
     New:       true
     Status:    enriched
     Generated: seo, linkedin, medium, social
[DEMO] Publishing article (website + Medium syndication bundle)...
  ✓ Published successfully
     Status:           published
     Website URL:      https://bytemind.fr/blogs/self-healing-data-pipeline-duckdb-python
     LinkedIn drafts:  content/drafts/linkedin/self-healing-data-pipeline-duckdb-python/
     Medium bundle:    content/published/medium/self-healing-data-pipeline-duckdb-python/
[DEMO] Fetching platform analytics...
  ✓ Platform stats
     Articles:    1
     Tokens used: 4521
     Published:   1

═══════════════════════════════════════════════════════════════
  DEMO COMPLETE — Full Article Lifecycle Executed
═══════════════════════════════════════════════════════════════
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `API not reachable` | Start with `uvicorn app.main:app --reload` |
| `ACTIONS_API_KEY not found` | Add to `.env` or `export ACTIONS_API_KEY=...` |
| `AI enrichment empty` | Check `GEMINI_API_KEY` in `.env` |
| `Publish fails: status pending` | Article needs enrichment first (re-run `/generate`) |
| `jq: command not found` | Install: `brew install jq` (macOS) or `apt install jq` |
