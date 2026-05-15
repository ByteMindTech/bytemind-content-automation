"""Add unique constraint on token_usage for upsert support.

Revision ID: 004_token_usage_unique
Revises: 003_content_hash
"""

revision = "004_token_usage_unique"
down_revision = "003_content_hash"

from alembic import op


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_token_usage_daily",
        "token_usage",
        ["date", "provider", "model", "prompt_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_token_usage_daily", "token_usage", type_="unique")
