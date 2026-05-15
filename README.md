# ByteMind Content Automation Platform

> AI-powered technical content lifecycle automation for [ByteMind](https://bytemind.fr)

[![CI](https://github.com/ByteMindTech/bytemind-content-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/ByteMindTech/bytemind-content-automation/actions)

## What it does

Detects new Markdown articles in the [ByteMindTech](https://github.com/ByteMindTech/ByteMindTech) website repo, enriches them with Gemini AI, generates SEO metadata + LinkedIn drafts, and publishes to the website as the primary source of truth. It also builds a Medium syndication bundle the operator can import manually.

```
src/content/blog/*.md  (ByteMindTech repo)
         ↓  GitHub Actions repository_dispatch
FastAPI API (OVH VPS / Docker)
         ↓
Gemini AI Engine  →  SEO + LinkedIn + Medium summaries
         ↓
Website publish recorded (source of truth: bytemind.fr)
         ↓
Medium syndication bundle  →  content/generated/medium/{slug}/
         ↓
LinkedIn drafts saved      →  content/generated/linkedin/{slug}/
         ↓
PostgreSQL  →  Analytics
```

### Publishing strategy

**bytemind.fr is the primary source of truth.**
Medium is used as a syndication/distribution channel, not as the origin.

| Target | How | When |
|--------|-----|------|
| Website | Recorded automatically on `POST /publish` | Always (default) |
| Medium (manual import) | Operator imports bundle at medium.com/me/import | After syndication bundle is generated |
| Medium (legacy API) | Optional token-based publish | Only for existing integration tokens |
| LinkedIn | Drafts saved to disk | Always — operator posts manually |

> **Medium API note:** Medium no longer issues new integration tokens as of January 2025.
> See: [Medium Help Center — API/Importing](https://help.medium.com/hc/en-us/articles/213480228-API-Importing)
> and the [official API repository](https://github.com/Medium/medium-api-docs).
> The recommended workflow is to use the generated syndication bundle for manual import at
> [medium.com/me/import](https://medium.com/me/import), which automatically applies
> a canonical URL back to your website — protecting your SEO.

## Quick Start (local dev)

### Prerequisites
- Docker + Docker Compose
- Python 3.12+ (for running tests locally)

### 1. Clone and configure

```bash
git clone https://github.com/ByteMindTech/bytemind-content-automation.git
cd bytemind-content-automation
cp .env.example .env
# Edit .env — set GEMINI_API_KEY, JWT_SECRET_KEY, ACTIONS_API_KEY
```

### 2. Start with Docker Compose

```bash
docker compose -f docker-compose.dev.yml up --build
```

The API is now running at [http://localhost:8000](http://localhost:8000)

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health:** http://localhost:8000/health

### 3. Generate content for an article

```bash
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer YOUR_ACTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_content": "---\ntitle: My Article\nslug: my-article\n..."
  }'
```

### 4. Publish an article (website-first)

```bash
curl -X POST http://localhost:8000/publish \
  -H "Authorization: Bearer YOUR_ACTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"article_id": "<uuid>", "publisher": "website"}'
```

Response includes:
- `website_url` — canonical URL on bytemind.fr
- `syndication_bundle_path` — path to the Medium import bundle
- `linkedin_drafts_folder` — path to LinkedIn post variants

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Platform status (no auth) |
| POST | `/generate` | Ingest + AI enrich an article |
| POST | `/publish` | Publish article (website + syndication bundle + LinkedIn drafts) |
| POST | `/schedule` | Schedule future publication |
| GET | `/articles` | List all articles |
| GET | `/analytics` | Platform metrics |
| GET | `/analytics/tokens` | Token usage by date |
| GET | `/analytics/published` | Published article list |

All endpoints except `/health` require `Authorization: Bearer <token>`.

### `POST /publish` — publisher options

| `publisher` value | Behaviour |
|-------------------|-----------|
| `website` (default) | Website publish record + Medium bundle + LinkedIn drafts |
| `medium` | + attempt token-based Medium API publish (requires existing `MEDIUM_INTEGRATION_TOKEN`) |
| `all` | Same as `medium` |

## Authentication

Two auth methods accepted:

1. **Static API key** (`ACTIONS_API_KEY` env var) — used by GitHub Actions
2. **JWT bearer token** — generated via `app/security/jwt.py`

## Configuration

All configuration is via environment variables. See `.env.example` for full reference.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `WEBSITE_BASE_URL` | `https://bytemind.fr` | Website source of truth |
| `MEDIUM_CANONICAL_BASE_URL` | `https://bytemind.fr/blogs` | Canonical URL base for syndication |
| `MEDIUM_DRY_RUN` | `true` | Skip real Medium API calls |
| `MEDIUM_INTEGRATION_TOKEN` | — | Optional: legacy token for token-based API publish |
| `AI_PROVIDER` | `auto` | `gemini` / `openai` / `auto` (fallback) |
| `GEMINI_API_KEY` | — | Required for AI enrichment |
| `SCHEDULER_PUBLISH_CRON` | `0 10 * * 5` | Friday 10 AM Paris |

## Project Structure

```
app/
├── api/            FastAPI routers + Pydantic schemas
├── ai/             Gemini/OpenAI engine, prompts, validator
├── analytics/      Metrics service
├── config/         Pydantic BaseSettings
├── linkedin/       LinkedIn draft generator
├── medium/
│   ├── publisher.py     Legacy token-based Medium API client
│   └── syndication.py   Syndication bundle exporter (no token required)
├── models/         SQLAlchemy 2.0 ORM models
├── repositories/   DB access layer (async)
├── scheduler/      APScheduler integration
├── security/       JWT + API key auth
├── services/       Content + Publishing orchestration
└── utils/          Markdown parser, structured logging

content/
├── generated/
│   ├── medium/{slug}/       Medium syndication bundles
│   │   ├── article.md       Full article with canonical URL in front-matter
│   │   ├── metadata.json    Structured metadata + optional API payload
│   │   └── README.md        Operator instructions for manual import
│   └── linkedin/{slug}/     LinkedIn post variants
```

## Medium Syndication Workflow

After calling `POST /publish`, a bundle is ready at `content/generated/medium/{slug}/`:

1. **Recommended — manual import:**
   - Go to [medium.com/me/import](https://medium.com/me/import)
   - Paste the canonical URL from `metadata.json`
   - Medium imports the article and applies the canonical link automatically (SEO-safe)

2. **Alternative — paste content:**
   - Copy the body from `article.md` (below the `---` front-matter block)
   - Create a new story on Medium
   - Set the canonical URL in story settings to the value in `metadata.json`

3. **Legacy — token-based API (existing tokens only):**
   - Use the `medium_api_payload` object in `metadata.json`
   - Call `POST /publish` with `"publisher": "medium"`

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check app/ tests/
mypy app/
```

## Deployment (OVH VPS)

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full OVH VPS setup guide.

```bash
docker compose up -d
```

GitHub Actions pushes to `main` automatically deploy to OVH VPS.
Required secrets: `OVH_VPS_HOST`, `OVH_VPS_USER`, `OVH_VPS_SSH_KEY`.

## Security

- All secrets via environment variables — never hardcoded
- Prompt injection protection in AI output validator
- JWT with configurable expiry
- Rate limiting on all endpoints
- GDPR: no PII stored in article content
- Audit log for all generate/publish actions
- TLS termination via Caddy (auto Let's Encrypt)

## License

Proprietary — ByteMind © 2024
