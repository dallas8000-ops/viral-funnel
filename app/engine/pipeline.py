from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.rank import rank
from app.engine.render import pool, render_pack
from app.engine.rewrite import rewrite_batch
from app.engine.scout import scout_all
from app.models import FactoryJob, OperatorConfig, PipelineRun, ScheduledPost, SourceItem
from app.settings import ASSET_DIR, get_settings


async def load_config(session: AsyncSession) -> OperatorConfig:
    row = await session.get(OperatorConfig, 1)
    if row is None:
        row = OperatorConfig(id=1)
        session.add(row)
        await session.flush()
    return row


def cfg_dict(row: OperatorConfig) -> dict[str, str]:
    return {
        "niche": row.niche,
        "voice": row.voice,
        "enemy": row.enemy,
        "promise": row.promise,
        "offer_name": row.offer_name or "the inner circle",
        "offer_bullets": row.offer_bullets,
    }


async def persist_hits(session: AsyncSession, scored) -> list[SourceItem]:
    saved: list[SourceItem] = []
    hashes = [hit.content_hash for hit, _ in scored]
    existing_rows = (
        await session.scalars(select(SourceItem).where(SourceItem.content_hash.in_(hashes)))
    ).all()
    by_hash = {r.content_hash: r for r in existing_rows}
    for hit, score in scored:
        row = by_hash.get(hit.content_hash)
        if row:
            row.score = max(row.score, score)
            saved.append(row)
            continue
        item = SourceItem(
            content_hash=hit.content_hash,
            platform=hit.platform,
            url=hit.url,
            title=hit.title,
            body=hit.body,
            score=score,
            raw={"ups": hit.ups, "comments": hit.comments, "extra": hit.extra},
        )
        session.add(item)
        saved.append(item)
    await session.flush()
    return saved


def next_slots(now: datetime, hours: list[int], tz: ZoneInfo, days: int) -> list[datetime]:
    local = now.astimezone(tz)
    slots: list[datetime] = []
    for d in range(0, days):
        day = (local + timedelta(days=d)).date()
        for h in hours:
            cand = datetime(day.year, day.month, day.day, h, 0, tzinfo=tz)
            if cand > local:
                slots.append(cand.astimezone(timezone.utc))
    return slots


async def fill_queue(session: AsyncSession, jobs: list[FactoryJob]) -> int:
    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    hours = settings.post_hour_list
    existing = (
        await session.scalars(
            select(ScheduledPost).where(ScheduledPost.status.in_(("pending", "publishing")))
        )
    ).all()
    taken = {p.publish_at.astimezone(timezone.utc).isoformat() for p in existing}
    slots = [
        s
        for s in next_slots(datetime.now(timezone.utc), hours, tz, settings.inventory_days)
        if s.isoformat() not in taken
    ]
    n = 0
    ready = [j for j in jobs if j.status == "ready"]
    for job, slot in zip(ready, slots, strict=False):
        session.add(
            ScheduledPost(job_id=job.id, kind="carousel", publish_at=slot, status="pending")
        )
        n += 1
    return n


async def run_factory(session: AsyncSession) -> dict:
    t0 = time.perf_counter()
    settings = get_settings()
    cfg = await load_config(session)
    if not cfg.niche.strip():
        return {"ok": False, "error": "Set niche before running the factory."}

    t_scout = time.perf_counter()
    subs = [s.strip() for s in cfg.subs.split(",") if s.strip()]
    hits = await scout_all(cfg.niche, subs)
    scored = rank(hits, cfg.niche, settings.scout_limit)
    items = await persist_hits(session, scored)
    scout_ms = int((time.perf_counter() - t_scout) * 1000)

    need = settings.post_hour_list.__len__() * settings.inventory_days
    used_ids = set(
        (await session.scalars(select(FactoryJob.source_id))).all()
    )
    todo = [i for i in items if i.id not in used_ids][:need]
    if not todo:
        return {
            "ok": True,
            "hits": len(hits),
            "kept": 0,
            "jobs": 0,
            "queued": 0,
            "scout_ms": scout_ms,
            "rewrite_ms": 0,
            "render_ms": 0,
            "total_ms": int((time.perf_counter() - t0) * 1000),
            "note": "No new source items after dedupe.",
        }

    t_rw = time.perf_counter()
    packs = await rewrite_batch([(i.title, i.body) for i in todo], cfg_dict(cfg))
    rewrite_ms = int((time.perf_counter() - t_rw) * 1000)

    t_render = time.perf_counter()
    executor = pool(settings.render_workers)
    offer = cfg.offer_name or "the inner circle"
    loop = asyncio.get_running_loop()

    async def render_job(item: SourceItem, pack: dict) -> FactoryJob:
        dest = str(ASSET_DIR / f"job_{item.id}")
        await loop.run_in_executor(
            executor, render_pack, dest, pack["slides"], pack["reel_script"], offer
        )
        job = FactoryJob(
            source_id=item.id,
            status="ready",
            hook=pack["hook"],
            caption=pack["caption"],
            reel_script=pack["reel_script"],
            slides=pack["slides"],
            asset_dir=dest,
        )
        session.add(job)
        return job

    jobs = list(await asyncio.gather(*[render_job(i, p) for i, p in zip(todo, packs, strict=True)]))
    await session.flush()
    render_ms = int((time.perf_counter() - t_render) * 1000)
    queued = await fill_queue(session, jobs)
    duration = int((time.perf_counter() - t0) * 1000)
    stats = {
        "hits": len(hits),
        "kept": len(todo),
        "jobs": len(jobs),
        "queued": queued,
        "scout_ms": scout_ms,
        "rewrite_ms": rewrite_ms,
        "render_ms": render_ms,
        "total_ms": duration,
    }
    session.add(PipelineRun(kind="factory", ok=1, stats=stats, duration_ms=duration))
    return {"ok": True, **stats}
