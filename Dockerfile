# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt --target /deps

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="ByteMind <contact@bytemind.fr>"
LABEL description="ByteMind Content Automation Platform"

# Security: non-root user
RUN groupadd --gid 1001 bytemind \
    && useradd --uid 1001 --gid 1001 --no-create-home bytemind

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Ensure content dirs exist (may not be in repo)
RUN mkdir -p content/generated/linkedin content/drafts content/published \
    && chown -R bytemind:bytemind /app

USER bytemind

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
