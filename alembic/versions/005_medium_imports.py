"""Add medium import queue tracking.

Revision ID: 005_medium_imports
Revises: 004_token_usage_unique
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "005_medium_imports"
down_revision = "004_token_usage_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medium_imports",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("website_url", sa.String(1024), nullable=False),
        sa.Column("canonical_url", sa.String(1024), nullable=False),
        sa.Column("medium_url", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("canonical_verified", sa.Boolean, server_default="false"),
        sa.Column("canonical_found", sa.String(1024), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_medium_imports_article_id", "medium_imports", ["article_id"])
    op.create_index("ix_medium_imports_status", "medium_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_medium_imports_status", table_name="medium_imports")
    op.drop_index("ix_medium_imports_article_id", table_name="medium_imports")
    op.drop_table("medium_imports")
