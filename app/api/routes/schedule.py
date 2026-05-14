"""POST /schedule — queue an article for future publication."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ScheduleRequest, ScheduleResponse
from app.repositories import AsyncSessionLocal, get_db
from app.repositories.article_repository import ArticleRepository
from app.scheduler.scheduler import scheduler
from app.security import require_api_key
from app.services.publishing_service import PublishingService

router = APIRouter()


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_202_ACCEPTED)
async def schedule_publish(
    body: ScheduleRequest,
    actor: Annotated[str, Depends(require_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleResponse:
    """
    Schedule an article for publication at a future datetime.
    The scheduler will call the publish pipeline at the specified time.
    """
    repo = ArticleRepository(db)
    article = await repo.get_by_id(body.article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Article {body.article_id} not found")

    async def _publish_fn(article_id, sched_actor, publisher):
        async with AsyncSessionLocal() as s:
            ps = PublishingService(s)
            await ps.publish_article(article_id, actor=sched_actor)
            await s.commit()

    job_id = scheduler.schedule_article(
        article_id=body.article_id,
        publish_fn=_publish_fn,
        run_at=body.scheduled_at,
        publisher=body.publisher,
    )

    return ScheduleResponse(
        article_id=str(body.article_id),
        job_id=job_id,
        scheduled_at=body.scheduled_at,
        publisher=body.publisher,
    )
