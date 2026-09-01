from __future__ import annotations

from contextlib import asynccontextmanager
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import init_db, session_scope
from app.engine.billing import checkout_url, handle_webhook, member_from_checkout_session
from app.engine.pipeline import load_config, run_factory
from app.engine.publisher import pack_public, publish_due
from app.engine.render import shutdown_pool
from app.engine.scheduler import start_scheduler
from app.engine.scoreboard import scoreboard
from app.engine.scout import close_http
from app.models import FactoryJob, Member, ScheduledPost, SourceItem
from app.settings import ASSET_DIR, get_settings

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    if "pytest" not in sys.modules:
        start_scheduler()
    yield
    await close_http()
    shutdown_pool()


app = FastAPI(title="Viral Funnel Engine", default_response_class=ORJSONResponse, lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ConfigIn(BaseModel):
    niche: str = Field(min_length=2, max_length=240)
    voice: str = ""
    enemy: str = ""
    promise: str = ""
    offer_name: str = ""
    offer_bullets: str = ""
    subs: str = "Entrepreneur,smallbusiness,marketing,sales"


def _html(name: str) -> HTMLResponse:
    path = STATIC / name
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
async def operator() -> HTMLResponse:
    return _html("operator.html")


@app.get("/join", response_class=HTMLResponse)
async def join() -> HTMLResponse:
    return _html("join.html")


@app.get("/community", response_class=HTMLResponse)
async def community() -> HTMLResponse:
    return _html("community.html")


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/scoreboard")
async def api_scoreboard() -> dict:
    async with session_scope() as session:
        return await scoreboard(session)


@app.get("/api/config")
async def get_config() -> dict:
    async with session_scope() as session:
        row = await load_config(session)
        return {
            "niche": row.niche,
            "voice": row.voice,
            "enemy": row.enemy,
            "promise": row.promise,
            "offer_name": row.offer_name,
            "offer_bullets": row.offer_bullets,
            "subs": row.subs,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }


@app.put("/api/config")
async def put_config(body: ConfigIn) -> dict:
    async with session_scope() as session:
        row = await load_config(session)
        for k, v in body.model_dump().items():
            setattr(row, k, v)
        return {"ok": True}


@app.post("/api/start")
async def start_clock() -> dict:
    from datetime import datetime, timezone

    async with session_scope() as session:
        row = await load_config(session)
        if not row.niche.strip():
            raise HTTPException(400, "Niche required")
        if row.started_at is None:
            row.started_at = datetime.now(timezone.utc)
        return {"started_at": row.started_at.isoformat()}


@app.post("/api/factory")
async def api_factory() -> dict:
    async with session_scope() as session:
        result = await run_factory(session)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "factory failed")
    return result


@app.post("/api/publish")
async def api_publish() -> dict:
    async with session_scope() as session:
        return await publish_due(session)


@app.get("/api/offer")
async def api_offer() -> dict:
    settings = get_settings()
    async with session_scope() as session:
        row = await load_config(session)
        return {
            "offer_name": row.offer_name or "Operator community",
            "promise": row.promise,
            "offer_bullets": row.offer_bullets,
            "price_cents": settings.stripe_price_cents,
        }


@app.get("/api/queue")
async def api_queue() -> dict:
    async with session_scope() as session:
        posts = (
            await session.scalars(select(ScheduledPost).order_by(ScheduledPost.publish_at.desc()).limit(60))
        ).all()
        jobs = {
            j.id: j
            for j in (
                await session.scalars(select(FactoryJob).where(FactoryJob.id.in_({p.job_id for p in posts} or {0})))
            ).all()
        }
        return {
            "posts": [
                {
                    "id": p.id,
                    "job_id": p.job_id,
                    "kind": p.kind,
                    "publish_at": p.publish_at.isoformat(),
                    "status": p.status,
                    "attempts": p.attempts,
                    "last_error": p.last_error,
                    "hook": (jobs.get(p.job_id).hook if jobs.get(p.job_id) else ""),
                    "asset_dir": (jobs.get(p.job_id).asset_dir if jobs.get(p.job_id) else ""),
                    "caption": (jobs.get(p.job_id).caption if jobs.get(p.job_id) else ""),
                    "pack_url": (pack_public(jobs[p.job_id])["pack_url"] if jobs.get(p.job_id) else ""),
                }
                for p in posts
            ]
        }


@app.get("/api/sources")
async def api_sources() -> dict:
    async with session_scope() as session:
        rows = (
            await session.scalars(select(SourceItem).order_by(SourceItem.score.desc()).limit(50))
        ).all()
        return {
            "items": [
                {
                    "id": r.id,
                    "platform": r.platform,
                    "title": r.title,
                    "score": r.score,
                    "url": r.url,
                }
                for r in rows
            ]
        }


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: int) -> dict:
    async with session_scope() as session:
        job = await session.get(FactoryJob, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        pack = pack_public(job)
        return {
            "id": job.id,
            "hook": job.hook,
            "caption": job.caption,
            "reel_script": job.reel_script,
            "slides": job.slides,
            "asset_dir": job.asset_dir,
            "status": job.status,
            **pack,
        }


class CheckoutIn(BaseModel):
    email: str | None = None


@app.post("/api/checkout")
async def api_checkout(body: CheckoutIn | None = None) -> dict:
    async with session_scope() as session:
        url = await checkout_url(session, body.email if body else None)
    return {"url": url}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    async with session_scope() as session:
        return await handle_webhook(request, session)


@app.get("/api/community")
async def api_community(token: str = "", session_id: str = "") -> dict:
    settings = get_settings()
    async with session_scope() as session:
        row = None
        if session_id:
            row = await member_from_checkout_session(session, session_id)
        elif token:
            row = await session.scalar(select(Member).where(Member.access_token == token))
        if row is None or row.status != "active":
            return {"ok": False}
        return {
            "ok": True,
            "email": row.email,
            "discord": settings.discord_invite_url,
            "token": row.access_token,
        }


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    ico = STATIC / "favicon.ico"
    if ico.exists():
        return FileResponse(ico)
    raise HTTPException(404)
