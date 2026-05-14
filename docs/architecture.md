# ByteMind Content Automation Platform

## Architecture Overview

```
                              OVH VPS (2GB RAM, ~€5/month)
┌──────────────────────────────────────────────────────────────────────┐
│  Caddy (reverse proxy, auto TLS)           ← ports 80/443           │
│       ↓                                                              │
│  FastAPI uvicorn (2 workers, 512MB cap)    ← port 8000 (internal)   │
│       ↓                                                              │
│  ┌─────────────────────────────────────────┐                         │
│  │ Multi-LLM Router                        │                         │
│  │ ├─ gemini-2.0-flash (cheap: tags, CTA)  │ ← external API calls   │
│  │ ├─ gemini-1.5-pro (complex: content)    │                         │
│  │ ├─ gpt-4o-mini (cheap fallback)         │                         │
│  │ └─ gpt-4o (complex fallback)            │                         │
│  └─────────────────────────────────────────┘                         │
│       ↓                                                              │
│  PostgreSQL 16 (128MB shared_buffers)      ← port 5432 (internal)   │
│  Redis 7 (64MB maxmemory)                  ← port 6379 (internal)   │
└──────────────────────────────────────────────────────────────────────┘
         ↑
   GitHub Actions (CI/CD, triggers)
         ↑
   ByteMindTech repo (src/content/blog/*.md)
```

## Content Pipeline Flow

```
New .md article in ByteMindTech repo
        ↓ (GitHub Actions dispatch)
Parse markdown + extract metadata
        ↓
Content hash check (skip if unchanged)
        ↓
AI Enrichment (8 prompts, concurrent with semaphore)
  ├─ seo_title          → gemini-2.0-flash
  ├─ seo_description    → gemini-2.0-flash
  ├─ hashtags           → gemini-2.0-flash
  ├─ cta                → gemini-2.0-flash
  ├─ linkedin_short     → gemini-1.5-pro
  ├─ linkedin_medium    → gemini-1.5-pro
  ├─ linkedin_technical → gemini-1.5-pro
  └─ medium_intro       → gemini-1.5-pro
        ↓
AI Final Revision (quality score 1-10)
        ↓
Score ≥ 9? → Auto-approve → Publish to Medium
Score < 9? → Email notification → User clicks Approve/Reject
        ↓
Approved → Publish to Medium (or dry-run)
Rejected → Article marked, can be re-enriched
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Application monitoring metrics |
| POST | `/generate` | Ingest + AI enrich an article |
| POST | `/publish` | Publish an article to Medium |
| POST | `/schedule` | Schedule future publication |
| GET | `/articles` | List articles with filters |
| GET | `/analytics` | Analytics dashboard data |
| GET | `/approval/approve/{token}` | Approve article (email link) |
| GET | `/approval/reject/{token}` | Reject article (email link) |

## Technology Stack

- **Runtime**: Python 3.12, FastAPI, Uvicorn
- **Database**: PostgreSQL 16 (async via asyncpg)
- **Cache/Rate-limit**: Redis 7
- **AI**: Google Gemini (primary), OpenAI GPT (fallback)
- **Reverse Proxy**: Caddy (auto-TLS)
- **Scheduler**: APScheduler with PostgreSQL job store
- **Auth**: JWT + API key
- **CI/CD**: GitHub Actions
- **Container**: Docker + Docker Compose
