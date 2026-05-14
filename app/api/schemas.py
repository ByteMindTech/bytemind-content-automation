"""Pydantic request/response schemas for the API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request schemas ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """POST /generate — trigger AI enrichment for an article."""

    source_content: str | None = Field(
        None, description="Raw Markdown content. If omitted, article_id must be provided."
    )
    article_id: uuid.UUID | None = Field(
        None, description="ID of an already-ingested article to re-enrich."
    )
    source_path: str = Field(default="", description="Optional source file path label.")


class PublishRequest(BaseModel):
    """POST /publish — publish an enriched article."""

    article_id: uuid.UUID
    publisher: str = Field(default="medium", description="Target publisher.")
    publish_status: str = Field(
        default="draft", description="medium publish status: draft | public | unlisted"
    )


class ScheduleRequest(BaseModel):
    """POST /schedule — queue an article for future publishing."""

    article_id: uuid.UUID
    scheduled_at: datetime = Field(description="ISO datetime for publication (UTC).")
    publisher: str = Field(default="medium")


class ArticleListParams(BaseModel):
    """GET /articles query params."""

    status: str | None = None
    category: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# ── Response schemas ─────────────────────────────────────────────────────────

class ArticleResponse(BaseModel):
    """Single article summary."""

    id: uuid.UUID
    slug: str
    title: str
    category: str
    tags: list[str]
    author: str
    status: str
    featured: bool
    read_time_minutes: int | None
    word_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateResponse(BaseModel):
    article_id: uuid.UUID
    is_new: bool
    generated_types: list[str]
    status: str


class PublishResponse(BaseModel):
    article_id: str
    slug: str
    medium: dict[str, Any]
    linkedin_drafts_folder: str | None
    status: str


class ScheduleResponse(BaseModel):
    article_id: str
    job_id: str
    scheduled_at: datetime
    publisher: str


class AnalyticsResponse(BaseModel):
    articles: dict[str, int]
    publishing: dict[str, int]
    ai: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    medium_dry_run: bool
    ai_provider: str
