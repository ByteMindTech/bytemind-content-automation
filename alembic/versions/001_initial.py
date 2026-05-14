"""Initial schema — all tables.

Revision ID: 001_initial
Revises: -
Create Date: 2025-05-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── articles ──────────────────────────────────────────────────────────────
    op.create_table(
        "articles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("category", sa.String(128), nullable=False, index=True),
        sa.Column("tags", ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("author_role", sa.String(255), nullable=True),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("date_label", sa.String(64), nullable=True),
        sa.Column("publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_time_minutes", sa.Integer, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("featured", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── ai_generations ────────────────────────────────────────────────────────
    op.create_table(
        "ai_generations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_type", sa.String(64), nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("output", sa.Text, nullable=False),
        sa.Column("output_validated", sa.Boolean, server_default="false"),
        sa.Column("tokens_input", sa.Integer, server_default="0"),
        sa.Column("tokens_output", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Float, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer, server_default="0"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── publishing_history ────────────────────────────────────────────────────
    op.create_table(
        "publishing_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("publisher", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("dry_run", sa.Boolean, server_default="false"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("raw_response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── scheduled_jobs ────────────────────────────────────────────────────────
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("publisher", sa.String(64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("apscheduler_job_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("success", sa.Boolean, server_default="true"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── token_usage ───────────────────────────────────────────────────────────
    op.create_table(
        "token_usage",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_type", sa.String(64), nullable=False),
        sa.Column("tokens_input", sa.Integer, server_default="0"),
        sa.Column("tokens_output", sa.Integer, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, server_default="0.0"),
        sa.Column("call_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("token_usage")
    op.drop_table("audit_logs")
    op.drop_table("scheduled_jobs")
    op.drop_table("publishing_history")
    op.drop_table("ai_generations")
    op.drop_table("articles")
