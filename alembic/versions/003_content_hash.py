"""Add content_hash to articles for change detection.

Revision ID: 003_content_hash
Revises: 002_approval_workflow
Create Date: 2025-05-15
"""

from alembic import op
import sqlalchemy as sa


revision = "003_content_hash"
down_revision = "002_approval_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_articles_content_hash", table_name="articles")
    op.drop_column("articles", "content_hash")
