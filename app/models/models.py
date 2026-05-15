"""SQLAlchemy 2.0 ORM models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base."""


class TimestampMixin:
    """Adds created_at / updated_at to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Article(TimestampMixin, Base):
    """Source Markdown article ingested from ByteMindTech repo."""

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    author_role: Mapped[str | None] = mapped_column(String(255))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    date_label: Mapped[str | None] = mapped_column(String(64))
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_time_minutes: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    # Status: pending | processing | enriched | revising | awaiting_approval |
    # approved | published | rejected | failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    generations: Mapped[list["AIGeneration"]] = relationship(
        "AIGeneration", back_populates="article", cascade="all, delete-orphan"
    )
    publish_records: Mapped[list["PublishingHistory"]] = relationship(
        "PublishingHistory", back_populates="article", cascade="all, delete-orphan"
    )
    scheduled_jobs: Mapped[list["ScheduledJob"]] = relationship(
        "ScheduledJob", back_populates="article", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["ArticleRevision"]] = relationship(
        "ArticleRevision", back_populates="article", cascade="all, delete-orphan"
    )


class AIGeneration(TimestampMixin, Base):
    """Record of an AI content generation call."""

    __tablename__ = "ai_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # gemini | openai
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. seo_title | seo_description | linkedin_short | linkedin_medium |
    #      linkedin_technical | medium_intro | hashtags | cta | readability
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    output_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    article: Mapped["Article"] = relationship("Article", back_populates="generations")


class PublishingHistory(TimestampMixin, Base):
    """Record of a publish event (Medium or other publisher)."""

    __tablename__ = "publishing_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publisher: Mapped[str] = mapped_column(String(64), nullable=False)  # medium | mock
    external_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | published | failed | dry_run
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    article: Mapped["Article"] = relationship("Article", back_populates="publish_records")


class ScheduledJob(TimestampMixin, Base):
    """Scheduled publication job."""

    __tablename__ = "scheduled_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publisher: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued"
    )  # queued | executed | cancelled | failed
    apscheduler_job_id: Mapped[str | None] = mapped_column(String(255))

    article: Mapped["Article"] = relationship("Article", back_populates="scheduled_jobs")


class MediumImport(TimestampMixin, Base):
    """Tracks Medium import lifecycle for published articles."""

    __tablename__ = "medium_imports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    website_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    medium_url: Mapped[str | None] = mapped_column(String(1024))
    # Status: queued | import_ready | imported | verified | canonical_mismatch | failed
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )
    canonical_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    canonical_found: Mapped[str | None] = mapped_column(String(1024))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    article: Mapped["Article"] = relationship("Article", backref="medium_imports")


class AuditLog(TimestampMixin, Base):
    """Immutable audit trail for generate/publish/schedule actions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # generate | publish | schedule | cancel
    actor: Mapped[str] = mapped_column(String(255), nullable=False)  # user/api-key identity
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)


class TokenUsage(TimestampMixin, Base):
    """Daily token usage aggregates per provider."""

    __tablename__ = "token_usage"
    __table_args__ = (
        UniqueConstraint("date", "provider", "model", "prompt_type", name="uq_token_usage_daily"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    call_count: Mapped[int] = mapped_column(Integer, default=0)


class ArticleRevision(TimestampMixin, Base):
    """AI revision review of enriched article content."""

    __tablename__ = "article_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    issues: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    suggestions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    article: Mapped["Article"] = relationship("Article", back_populates="revisions")
