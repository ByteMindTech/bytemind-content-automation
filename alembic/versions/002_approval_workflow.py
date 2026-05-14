"""Add article_revisions table and update article status flow.

Revision ID: 002_approval_workflow
Revises: 001_initial
Create Date: 2025-05-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "002_approval_workflow"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("quality_score", sa.Integer, nullable=False),
        sa.Column("auto_approved", sa.Boolean, server_default="false"),
        sa.Column("issues", JSONB, nullable=True),
        sa.Column("suggestions", JSONB, nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("tokens_input", sa.Integer, server_default="0"),
        sa.Column("tokens_output", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("article_revisions")
