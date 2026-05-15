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
│  │ ├─ gemini-2.5-flash (cheap: tags, CTA)  │ ← external API calls   │
│  │ ├─ gemini-2.5-pro (complex: content)    │                         │
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

## Publishing Strategy

**bytemind.fr is the primary source of truth.**

```
New .md article in ByteMindTech repo
        ↓ (GitHub Actions dispatch)
Parse markdown + extract metadata
        ↓
Content hash check (skip if unchanged)
        ↓
AI Enrichment (8 prompts, concurrent with semaphore)
  ├─ seo_title          → gemini-2.5-flash
  ├─ seo_description    → gemini-2.5-flash
  ├─ hashtags           → gemini-2.5-flash
  ├─ cta                → gemini-2.5-flash
  ├─ linkedin_short     → gemini-2.5-pro
  ├─ linkedin_medium    → gemini-2.5-pro
  ├─ linkedin_technical → gemini-2.5-pro
  └─ medium_intro       → gemini-2.5-pro
        ↓
AI Final Revision (quality score 1-10)
        ↓
Score ≥ 9? → Auto-approve
Score < 9? → Email notification → Approve / Reject
        ↓ (on approval)
POST /publish (publisher="website")
  ├─ Record website publication (source of truth)
  ├─ Build Medium syndication bundle → content/generated/medium/{slug}/
  │    ├─ article.md       (canonical URL in front-matter)
  │    ├─ metadata.json    (structured metadata + optional API payload)
  │    └─ README.md        (operator instructions for manual import)
  └─ Save LinkedIn drafts → content/generated/linkedin/{slug}/
        ↓
Operator:
  - Imports/publishes Medium bundle manually at medium.com/me/import
  - Posts LinkedIn draft manually
```

### Why website-first?

- **SEO ownership**: canonical URLs point to bytemind.fr, not Medium.
- **No API dependency**: Medium stopped issuing new integration tokens in January 2025.
  Reference: https://github.com/Medium/medium-api-docs
  Reference: https://help.medium.com/hc/en-us/articles/213480228-API-Importing
- **Resilience**: the pipeline runs fully even if Medium is unavailable.
- **Content permanence**: all content stays in the git repository.

### Medium API status

> The Medium API is no longer supported. No new integration tokens are issued.
> Browser-based OAuth is supported for existing integrations only.
> — [github.com/Medium/medium-api-docs](https://github.com/Medium/medium-api-docs)

**Supported paths:**

| Path | Requires | Recommended |
|------|----------|-------------|
| Manual import via medium.com/me/import | None (uses bundle) | ✅ Yes |
| Paste content + set canonical | None | ✅ Yes |
| Token-based API publish | Pre-existing integration token | Optional |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Application monitoring metrics |
| POST | `/generate` | Ingest + AI enrich an article |
| POST | `/publish` | Publish article (website + syndication bundle) |
| POST | `/schedule` | Schedule future publication |
| GET | `/articles` | List articles with filters |
| GET | `/analytics` | Analytics dashboard data |
| GET | `/approval/approve/{token}` | Approve article (email link) |
| GET | `/approval/reject/{token}` | Reject article (email link) |

## Technology Stack

- **Runtime**: Python 3.12, FastAPI, Uvicorn
- **Database**: PostgreSQL 16 (async via asyncpg)
- **Cache/Rate-limit**: Redis 7
- **AI**: Google Gemini 2.5 Flash/Pro (primary), OpenAI GPT (fallback)
- **Reverse Proxy**: Caddy (auto-TLS via Let's Encrypt)
- **Scheduler**: APScheduler with PostgreSQL job store
- **Auth**: JWT + API key
- **CI/CD**: GitHub Actions
- **Container**: Docker + Docker Compose
