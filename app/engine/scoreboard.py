from __future__ import annotations

import secrets
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, OperatorConfig, ScheduledPost
from app.settings import get_settings


def members_needed() -> int:
    s = get_settings()
    return ceil(s.mrr_target_cents / s.stripe_price_cents)


def mrr_cents(active: int) -> int:
    return active * get_settings().stripe_price_cents


def day_index(started: datetime | None) -> int:
    if started is None:
        return 0
    delta = datetime.now(timezone.utc) - started.replace(tzinfo=started.tzinfo or timezone.utc)
    return max(int(delta.total_seconds() // 86400) + 1, 1)


def verdict(day: int, paid: int) -> dict:
    """Kill criteria. 103 paid by day 30. Linear pace is a lie after day 7."""
    need = members_needed()
    mrr = mrr_cents(paid)
    target = get_settings().mrr_target_cents
    pace_needed = need / 30
    expected = pace_needed * min(day, 30)
    gap = expected - paid

    if day <= 0:
        status, line = "NOT_STARTED", "Clock is not running. Lock niche, offer, voice, then start."
    elif day >= 30 and mrr < target:
        status, line = "FAILED", f"Day {day}. ${mrr/100:.0f} MRR. Bar was $5,000. Kill or rebuild the offer."
    elif day >= 30:
        status, line = "HIT", f"Day {day}. ${mrr/100:.0f} MRR. Bar cleared."
    elif day >= 14 and paid < 15:
        status, line = "KILL_WARNING", (
            f"Day {day}: {paid} paid. You needed ~{expected:.0f} on a linear lie, "
            "and 15 as a real floor. Distribution is broken. Buy traffic or stop."
        )
    elif day >= 7 and paid < 3:
        status, line = "OFF_PACE", (
            f"Day {day}: {paid} paid. Organic from zero will not hit 103. "
            "Ads + DM + warm list, or this dies."
        )
    else:
        status, line = "RUNNING", f"Day {day}: {paid}/{need} members. Gap vs linear: {gap:.1f}."

    return {
        "status": status,
        "line": line,
        "day": day,
        "paid": paid,
        "need": need,
        "mrr_cents": mrr,
        "target_cents": target,
        "sales_per_day_required": round(max(need - paid, 0) / max(30 - day, 1), 2),
    }


async def scoreboard(session: AsyncSession) -> dict:
    cfg = await session.get(OperatorConfig, 1)
    paid = int(
        await session.scalar(
            select(func.count()).select_from(Member).where(Member.status == "active")
        )
        or 0
    )
    pending = int(
        await session.scalar(
            select(func.count()).select_from(ScheduledPost).where(ScheduledPost.status == "pending")
        )
        or 0
    )
    published = int(
        await session.scalar(
            select(func.count())
            .select_from(ScheduledPost)
            .where(ScheduledPost.status.in_(("published", "exported")))
        )
        or 0
    )
    started = cfg.started_at if cfg else None
    board = verdict(day_index(started), paid)
    board.update(
        {
            "niche": cfg.niche if cfg else "",
            "offer_name": cfg.offer_name if cfg else "",
            "queue_depth": pending,
            "posted": published,
            "started_at": started.isoformat() if started else None,
        }
    )
    return board


def new_access_token() -> str:
    return secrets.token_urlsafe(24)
