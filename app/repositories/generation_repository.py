"""AI Generation repository."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIGeneration, TokenUsage


class AIGenerationRepository:
    """Stores and retrieves AI generation records + token usage aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> AIGeneration:
        record = AIGeneration(**data)
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_by_article(self, article_id: uuid.UUID) -> list[AIGeneration]:
        result = await self._session.execute(
            select(AIGeneration)
            .where(AIGeneration.article_id == article_id)
            .order_by(AIGeneration.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_latest_by_type(
        self, article_id: uuid.UUID, prompt_type: str
    ) -> AIGeneration | None:
        result = await self._session.execute(
            select(AIGeneration)
            .where(
                AIGeneration.article_id == article_id,
                AIGeneration.prompt_type == prompt_type,
            )
            .order_by(AIGeneration.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def record_token_usage(
        self,
        *,
        date: "datetime",
        provider: str,
        model: str,
        prompt_type: str,
        tokens_input: int,
        tokens_output: int,
        cost_usd: float,
    ) -> None:
        """Upsert daily token usage aggregate."""
        from datetime import datetime

        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(TokenUsage).values(
            date=date,
            provider=provider,
            model=model,
            prompt_type=prompt_type,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            total_cost_usd=cost_usd,
            call_count=1,
        )
        # On conflict (date, provider, model, prompt_type): accumulate
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "provider", "model", "prompt_type"],
            set_={
                "tokens_input": TokenUsage.tokens_input + tokens_input,
                "tokens_output": TokenUsage.tokens_output + tokens_output,
                "total_cost_usd": TokenUsage.total_cost_usd + cost_usd,
                "call_count": TokenUsage.call_count + 1,
            },
        )
        await self._session.execute(stmt)

    async def total_cost_usd(
        self, provider: str | None = None
    ) -> float:
        q = select(func.sum(AIGeneration.cost_usd))
        if provider:
            q = q.where(AIGeneration.provider == provider)
        result = await self._session.execute(q)
        return result.scalar_one_or_none() or 0.0
