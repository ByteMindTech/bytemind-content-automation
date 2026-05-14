"""APScheduler-based publishing scheduler."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class ContentScheduler:
    """
    Wraps APScheduler for content publication scheduling.

    Default cron: every Friday at 10:00 AM Europe/Paris.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(
            timezone=pytz.timezone(_settings.scheduler_timezone)
        )
        self._jobs: dict[str, str] = {}  # article_id → apscheduler job id

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler_started", timezone=_settings.scheduler_timezone)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    def schedule_article(
        self,
        article_id: uuid.UUID,
        publish_fn: "Callable",
        run_at: datetime,
        publisher: str = "medium",
    ) -> str:
        """Schedule a one-time publish job. Returns the APScheduler job ID."""
        job_id = f"publish-{article_id}-{int(run_at.timestamp())}"
        self._scheduler.add_job(
            publish_fn,
            trigger="date",
            run_date=run_at,
            args=[article_id, "scheduler", publisher],
            id=job_id,
            replace_existing=True,
        )
        self._jobs[str(article_id)] = job_id
        logger.info("job_scheduled", article_id=str(article_id), run_at=run_at.isoformat())
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        try:
            self._scheduler.remove_job(job_id)
            logger.info("job_cancelled", job_id=job_id)
            return True
        except Exception:
            return False

    def add_weekly_sweep(self, sweep_fn: "Callable") -> None:
        """Add the default weekly publish sweep (Friday 10 AM)."""
        parts = _settings.scheduler_publish_cron.split()
        if len(parts) != 5:
            logger.warning("invalid_cron", cron=_settings.scheduler_publish_cron)
            return
        minute, hour, day, month, dow = parts
        self._scheduler.add_job(
            sweep_fn,
            trigger=CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=dow,
                timezone=pytz.timezone(_settings.scheduler_timezone),
            ),
            id="weekly-publish-sweep",
            replace_existing=True,
        )
        logger.info(
            "weekly_sweep_scheduled",
            cron=_settings.scheduler_publish_cron,
            timezone=_settings.scheduler_timezone,
        )


# Module-level singleton — shared across FastAPI lifespan
scheduler = ContentScheduler()
