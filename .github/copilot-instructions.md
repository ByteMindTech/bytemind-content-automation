# ByteMind Content Automation — Copilot Instructions

## Commands

```bash
pip install -e ".[dev]"    # install all dependencies (inc. dev)
pytest                     # run test suite (requires PostgreSQL)
ruff check app/ tests/     # lint
mypy app/                  # type-check
docker compose -f docker-compose.dev.yml up --build  # full local stack
```

## Architecture

**ByteMind Content Automation** is a Python 3.12 + FastAPI platform that automates the technical content lifecycle for [bytemind.fr](https://bytemind.fr). It detects new Markdown blog posts in the ByteMindTech website repo, enriches them with Gemini AI, generates SEO metadata + LinkedIn summaries, publishes to Medium, and tracks analytics.

### Flow

```
src/content/blog/*.md  (ByteMindTech repo)
         ↓  GitHub Actions repository_dispatch
FastAPI API  (OVH VPS / Docker)
         ↓
Gemini AI Engine  →  SEO + LinkedIn + Medium summaries
         ↓
Medium Publisher (dry-run by default)
         ↓
LinkedIn Drafts  →  content/generated/linkedin/
         ↓
PostgreSQL  →  Analytics
```

### Project Structure

```
app/
├── ai/             Gemini/OpenAI engine, prompts, output validator
├── analytics/      Metrics service
├── api/            FastAPI routers (routes/) + Pydantic schemas
├── config/         Pydantic BaseSettings (settings.py)
├── linkedin/       LinkedIn draft generator
├── medium/         Medium API publisher
├── models/         SQLAlchemy 2.0 ORM models
├── repositories/   Async DB access layer (asyncpg)
├── scheduler/      APScheduler integration
├── security/       JWT + API key auth (auth.py, jwt.py)
├── services/       Content + Publishing + Email + Revision orchestration
└── utils/          Markdown parser, structured logging
alembic/            Database migrations (Alembic)
content/            Generated outputs (linkedin drafts, etc.)
infrastructure/     Docker + Terraform configs
tests/              pytest suite (unit, integration, api, security)
scripts/            Utility scripts
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

Two auth methods:
1. **Static API key** (`ACTIONS_API_KEY` env var) — used by GitHub Actions
2. **JWT bearer token** — generated via `app/security/jwt.py`

## Configuration

All configuration uses **environment variables** parsed by Pydantic `BaseSettings` in `app/config/settings.py`. See `.env.example` for full reference.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `development` / `production` |
| `AI_PROVIDER` | `auto` | `gemini` / `openai` / `auto` (fallback) |
| `GEMINI_API_KEY` | — | Required for AI enrichment |
| `MEDIUM_DRY_RUN` | `true` | Skip real Medium API calls |
| `SCHEDULER_PUBLISH_CRON` | `0 10 * * 5` | Friday 10 AM Paris |
| `AUTO_APPROVE_THRESHOLD` | `9` | Quality score for auto-approve |

## Key Conventions

### Async-first
- All DB access is async via SQLAlchemy 2.0 + asyncpg
- Use `async def` for route handlers and service methods
- Repository layer uses `AsyncSession`

### Layered architecture
```
Routes (api/) → Services (services/) → Repositories (repositories/)
                     ↕                        ↕
               AI Engine (ai/)          Database (models/)
```
- **Routes** handle HTTP, validation, auth — delegate to services
- **Services** contain business logic, orchestrate AI + DB + publishing
- **Repositories** are pure data-access (async SQLAlchemy queries)
- **Models** are SQLAlchemy 2.0 declarative ORM classes

### Type hints & validation
- All functions require complete type annotations (mypy strict mode)
- Use Pydantic v2 models for request/response schemas (in `api/schemas.py`)
- Settings validated at startup via `pydantic-settings`

### Logging
- Use `structlog` via `app.utils.logging.get_logger(__name__)`
- Log structured key-value pairs, not format strings
- Example: `logger.info("article_generated", slug=slug, tokens_used=count)`

### Error handling
- Services raise domain exceptions; routes catch and return proper HTTP responses
- Global exception handler in `app/main.py` catches unhandled errors
- Use `tenacity` for retries on external API calls (Gemini, Medium)

### Testing
- Tests in `tests/` (unit, integration, api, security subdirs)
- `pytest-asyncio` with `asyncio_mode = "auto"`
- Use `httpx.AsyncClient` for API testing
- Mock external APIs with `respx`
- Coverage target: `--cov=app`

### Security
- Never hardcode secrets — always use environment variables
- Prompt injection protection in `app/ai/validator.py`
- Rate limiting via `slowapi` on all endpoints
- JWT with configurable expiry
- CORS configured via env var

### Database migrations
- Alembic for schema migrations (`alembic/`)
- In development, tables auto-create via `Base.metadata.create_all`
- In production, always use `alembic upgrade head`

### Docker
- Multi-stage Dockerfile (builder → runtime)
- Non-root user (`bytemind:1001`)
- Production stack: Caddy (auto-TLS) → FastAPI → PostgreSQL + Redis
- Dev stack: `docker-compose.dev.yml` (hot-reload, exposed ports)

### CI/CD (GitHub Actions)
- `ci.yml` — lint (ruff) + type-check (mypy) + test (pytest) + Docker build
- `deploy.yml` — deploy to OVH VPS on push to `main`
- `dispatch-on-new-blog.yml` — trigger enrichment when new blog detected
- `enrich.yml` — AI enrichment workflow

### Code style
- Formatter: `black` (line-length 100)
- Linter: `ruff` (E, F, I, N, UP, B, SIM, ANN rules)
- Target: Python 3.12+
- Use `from __future__ import annotations` is NOT needed (3.12+ native)
