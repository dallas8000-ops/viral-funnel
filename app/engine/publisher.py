from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FactoryJob, PipelineRun, ScheduledPost
from app.settings import get_settings


async def due_posts(session: AsyncSession) -> list[ScheduledPost]:
    now = datetime.now(timezone.utc)
    stale = now - timedelta(minutes=10)
    await session.execute(
        update(ScheduledPost)
        .where(ScheduledPost.status == "publishing", ScheduledPost.publish_at < stale)
        .values(status="pending")
    )
    rows = (
        await session.scalars(
            select(ScheduledPost)
            .where(ScheduledPost.status == "pending", ScheduledPost.publish_at <= now)
            .order_by(ScheduledPost.publish_at)
            .limit(6)
        )
    ).all()
    return list(rows)


async def _ig_publish(job: FactoryJob) -> str:
    settings = get_settings()
    token = settings.meta_page_access_token
    ig = settings.meta_ig_user_id
    if not token or not ig:
        return "export"

    slides = sorted(Path(job.asset_dir).glob("slide_*.png"))
    if not slides:
        raise RuntimeError("no slides")
    public = settings.public_url.rstrip("/")
    image_url = f"{public}/assets/{Path(job.asset_dir).name}/{slides[0].name}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        create = await client.post(
            f"https://graph.facebook.com/v21.0/{ig}/media",
            data={
                "image_url": image_url,
                "caption": job.caption,
                "access_token": token,
            },
        )
        create.raise_for_status()
        creation_id = create.json()["id"]
        for _ in range(12):
            st = await client.get(
                f"https://graph.facebook.com/v21.0/{creation_id}",
                params={"fields": "status_code", "access_token": token},
            )
            code = (st.json() or {}).get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                break
            if code == "ERROR":
                raise RuntimeError(st.text)
            await asyncio.sleep(2)
        pub = await client.post(
            f"https://graph.facebook.com/v21.0/{ig}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
        )
        pub.raise_for_status()
        return pub.json().get("id", "published")


async def publish_due(session: AsyncSession) -> dict:
    posts = await due_posts(session)
    published = 0
    exported = 0
    errors = 0
    for post in posts:
        post.status = "publishing"
        post.attempts += 1
        job = await session.get(FactoryJob, post.job_id)
        if job is None:
            post.status = "failed"
            post.last_error = "missing job"
            errors += 1
            continue
        try:
            result = await _ig_publish(job)
            if result == "export":
                post.status = "exported"
                post.published_url = job.asset_dir
                exported += 1
            else:
                post.status = "published"
                post.published_url = result
                published += 1
        except Exception as exc:
            post.status = "pending" if post.attempts < 5 else "failed"
            post.last_error = str(exc)[:500]
            errors += 1
    session.add(
        PipelineRun(
            kind="publish",
            ok=1 if errors == 0 else 0,
            stats={"published": published, "exported": exported, "errors": errors},
        )
    )
    return {"published": published, "exported": exported, "errors": errors, "n": len(posts)}
