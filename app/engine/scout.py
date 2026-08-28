from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.settings import get_settings


@dataclass(slots=True)
class RawHit:
    platform: str
    url: str
    title: str
    body: str
    ups: float
    comments: float
    created_ts: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        key = " ".join(self.title.lower().split())
        return hashlib.sha256(key.encode()).hexdigest()

    @property
    def age_hours(self) -> float:
        return max((time.time() - self.created_ts) / 3600, 0.25)

    @property
    def velocity(self) -> float:
        return self.ups / self.age_hours


_CLIENT: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None:
        settings = get_settings()
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=4.0),
            limits=httpx.Limits(
                max_connections=settings.scout_concurrency,
                max_keepalive_connections=settings.scout_concurrency,
            ),
            http2=True,
            headers={"User-Agent": "ViralFunnelEngine/1.0 (operator; research)"},
            follow_redirects=True,
        )
    return _CLIENT


async def close_http() -> None:
    global _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
        _CLIENT = None


async def _get_json(url: str) -> Any | None:
    try:
        r = await http_client().get(url)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


async def scout_reddit(subs: list[str]) -> list[RawHit]:
    async def one(sub: str) -> list[RawHit]:
        data = await _get_json(f"https://www.reddit.com/r/{sub}/hot.json?limit=50&raw_json=1")
        if not data:
            return []
        hits: list[RawHit] = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data") or {}
            if d.get("stickied") or d.get("over_18"):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            created = float(d.get("created_utc") or time.time())
            hits.append(
                RawHit(
                    platform="reddit",
                    url=f"https://www.reddit.com{d.get('permalink') or ''}",
                    title=title,
                    body=(d.get("selftext") or "")[:2000],
                    ups=float(d.get("ups") or 0),
                    comments=float(d.get("num_comments") or 0),
                    created_ts=created,
                    extra={"sub": sub},
                )
            )
        return hits

    chunks = await asyncio.gather(*[one(s.strip()) for s in subs if s.strip()])
    out: list[RawHit] = []
    for c in chunks:
        out.extend(c)
    return out


async def scout_hn() -> list[RawHit]:
    data = await _get_json(
        "https://hn.algolia.com/api/v1/search?tags=story&numericFilters=points>80&hitsPerPage=50"
    )
    if not data:
        return []
    hits: list[RawHit] = []
    for h in data.get("hits") or []:
        title = (h.get("title") or "").strip()
        if not title:
            continue
        created = h.get("created_at_i") or time.time()
        hits.append(
            RawHit(
                platform="hn",
                url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                title=title,
                body="",
                ups=float(h.get("points") or 0),
                comments=float(h.get("num_comments") or 0),
                created_ts=float(created),
            )
        )
    return hits


async def scout_rss(feeds: list[str]) -> list[RawHit]:
    import re
    from email.utils import parsedate_to_datetime

    item_re = re.compile(r"<item>(.*?)</item>", re.I | re.S)
    title_re = re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.I | re.S)
    link_re = re.compile(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", re.I | re.S)
    date_re = re.compile(r"<pubDate>(.*?)</pubDate>", re.I | re.S)

    async def one(url: str) -> list[RawHit]:
        try:
            r = await http_client().get(url)
            if r.status_code != 200:
                return []
            text = r.text
        except Exception:
            return []
        hits: list[RawHit] = []
        for block in item_re.findall(text)[:30]:
            tm = title_re.search(block)
            lm = link_re.search(block)
            dm = date_re.search(block)
            if not tm:
                continue
            ts = time.time()
            if dm:
                try:
                    ts = parsedate_to_datetime(dm.group(1).strip()).timestamp()
                except Exception:
                    pass
            hits.append(
                RawHit(
                    platform="rss",
                    url=(lm.group(1).strip() if lm else url),
                    title=tm.group(1).strip(),
                    body="",
                    ups=20,
                    comments=0,
                    created_ts=ts,
                    extra={"feed": url},
                )
            )
        return hits

    if not feeds:
        return []
    chunks = await asyncio.gather(*[one(u) for u in feeds])
    out: list[RawHit] = []
    for c in chunks:
        out.extend(c)
    return out


def google_news_feed(niche: str) -> str:
    q = niche.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


async def scout_all(niche: str, subs: list[str]) -> list[RawHit]:
    feeds = [google_news_feed(niche)] if niche else []
    reddit, hn, rss = await asyncio.gather(
        scout_reddit(subs or ["Entrepreneur"]),
        scout_hn(),
        scout_rss(feeds),
    )
    merged = reddit + hn + rss
    seen: set[str] = set()
    unique: list[RawHit] = []
    for h in merged:
        if h.content_hash in seen:
            continue
        seen.add(h.content_hash)
        unique.append(h)
    return unique


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
