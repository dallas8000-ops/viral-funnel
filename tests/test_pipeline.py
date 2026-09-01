from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.engine.pipeline import fill_queue, next_slots
from app.models import FactoryJob, ScheduledPost


def test_next_slots_skips_hours_already_passed_today() -> None:
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 8, 29, 13, 0, tzinfo=tz)
    slots = next_slots(now.astimezone(timezone.utc), [8, 12, 18], tz, days=1)
    hours = [s.astimezone(tz).hour for s in slots]
    assert hours == [18]


async def test_fill_queue_schedules_ready_jobs_not_in_the_current_batch(session) -> None:
    session.add(
        FactoryJob(
            source_id=9,
            status="ready",
            hook="Stop posting for likes",
            caption="Join the room",
            slides=["a"] * 7,
            asset_dir="job_9",
        )
    )
    await session.flush()
    queued = await fill_queue(session, jobs=[])
    assert queued == 1
    post = (await session.scalars(select(ScheduledPost))).one()
    assert post.status == "pending"
    assert post.kind == "carousel"
