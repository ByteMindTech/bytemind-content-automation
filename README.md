# ByteMind Content Automation Platform

> AI-powered technical content lifecycle automation for [ByteMind](https://bytemind.fr)

[![CI](https://github.com/ByteMindTech/bytemind-content-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/ByteMindTech/bytemind-content-automation/actions)

## What it does

Detects new Markdown articles in the [ByteMindTech](https://github.com/ByteMindTech/ByteMindTech) website repo, enriches them with Gemini AI, generates SEO metadata + LinkedIn summaries, publishes to Medium, and tracks everything.

```
src/content/blog/*.md  (ByteMindTech repo)
         ↓  GitHub Actions repository_dispatch
FastAPI API (OVH VPS / Docker)
         ↓
Gemini AI Engine  →  SEO + LinkedIn + Medium summaries
         ↓
Medium Publisher (dry-run by default)
         ↓
LinkedIn Drafts saved to content/generated/linkedin/
         ↓
PostgreSQL  →  Analytics
```

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
# Using the ACTIONS_API_KEY from your .env
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer YOUR_ACTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_content": "---\ntitle: My Article\nslug: my-article\n..."
  }'
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Platform status (no auth) |
| POST | `/generate` | Ingest + AI enrich an article |
| POST | `/publish` | Publish to Medium |
| POST | `/schedule` | Schedule future publication |
| GET | `/articles` | List all articles |
| GET | `/analytics` | Platform metrics |
| GET | `/analytics/tokens` | Token usage by date |
| GET | `/analytics/published` | Published article list |

All endpoints except `/health` require `Authorization: Bearer <token>`.

## Authentication

Two auth methods accepted:

1. **Static API key** (`ACTIONS_API_KEY` env var) — used by GitHub Actions
2. **JWT bearer token** — generated via `app/security/jwt.py`

## Configuration

All configuration is via environment variables. See `.env.example` for full reference.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `MEDIUM_DRY_RUN` | `true` | Skip real Medium API calls |
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
├── medium/         Medium API publisher
├── models/         SQLAlchemy 2.0 ORM models
├── repositories/   DB access layer (async)
├── scheduler/      APScheduler integration
├── security/       JWT + API key auth
├── services/       Content + Publishing orchestration
└── utils/          Markdown parser, structured logging
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check app/ tests/

# Type check
mypy app/
```

## Deployment (OVH VPS)

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full OVH VPS setup guide.

```bash
# Production stack
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
- TLS termination at OVH reverse proxy (nginx)

## License

Proprietary — ByteMind © 2024
