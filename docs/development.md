# Local Development Guide

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Git

## Quick Start

```bash
# Clone
git clone https://github.com/ByteMindTech/bytemind-content-automation.git
cd bytemind-content-automation

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
# Edit .env with your API keys (GEMINI_API_KEY, OPENAI_API_KEY)

# Start infrastructure (PostgreSQL + Redis)
docker compose -f docker-compose.dev.yml up -d

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Running Tests

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/unit/test_markdown_parser.py -v
```

## Code Quality

```bash
# Format
black app/ tests/

# Lint
ruff check app/ tests/

# Type check
mypy app/
```

## Docker Development

```bash
# Full stack with hot-reload
docker compose -f docker-compose.dev.yml up

# Rebuild after dependency changes
docker compose -f docker-compose.dev.yml build
```

## Project Structure

```
app/
├── ai/           # AI engine, prompts, validator
├── api/          # FastAPI routes
├── config/       # Pydantic settings
├── medium/       # Medium publisher client
├── linkedin/     # LinkedIn draft generator
├── models/       # SQLAlchemy ORM models
├── repositories/ # Database access layer
├── scheduler/    # APScheduler (PostgreSQL-backed)
├── security/     # JWT + API key auth
├── services/     # Business logic orchestration
└── utils/        # Logging, markdown parser
```

## Testing an Article Enrichment

```bash
# Using curl (requires ACTIONS_API_KEY from .env)
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer YOUR_ACTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_content": "---\ntitle: Test Article\ntags: [ai]\ncategory: ai\n---\n\n# Hello World\n\nThis is a test article about AI.",
    "source_path": "test.md"
  }'
```
