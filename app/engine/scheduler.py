from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db import session_scope
from app.engine.pipeline import run_factory
from app.engine.publisher import publish_due
from app.settings import get_settings

scheduler = AsyncIOScheduler()


async def _factory_job() -> None:
    async with session_scope() as session:
        await run_factory(session)


async def _publish_job() -> None:
    async with session_scope() as session:
        await publish_due(session)


def start_scheduler() -> None:
    if scheduler.running:
        return
    hours = get_settings().post_hour_list
    hour_expr = ",".join(str(h) for h in hours)
    scheduler.add_job(
        _factory_job,
        CronTrigger(hour=3, minute=10),
        id="daily_factory",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _publish_job,
        CronTrigger(hour=hour_expr, minute=0),
        id="slot_publish",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _publish_job,
        IntervalTrigger(minutes=2),
        id="publish_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
