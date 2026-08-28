from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from app.settings import get_settings

SYSTEM = """You are a conversion copywriter for a paid community.
Rewrite source material into ORIGINAL commentary in the operator's voice.
Do not copy sentences. Steal the ANGLE, not the words.
Output strict JSON with keys:
hook (max 12 words),
slides (array of 7 strings, each max 18 words: hook, problem, insight, step, step, proof, cta),
caption (max 400 chars, 1 CTA, 3 hashtags max),
reel_script (15-25 seconds, spoken lines separated by | ),
cta (one line pointing to the $49/mo community).
"""


def _fallback(title: str, cfg: dict[str, str]) -> dict[str, Any]:
    offer = cfg.get("offer_name") or "the room"
    promise = cfg.get("promise") or "get the system"
    enemy = cfg.get("enemy") or "busywork that looks like work"
    hook = title[:72].rstrip(".")
    slides = [
        hook,
        f"Most people lose to {enemy}.",
        f"The job is {promise} — not more content.",
        "Pick one offer. Kill everything else.",
        "Post 3x/day. Same CTA. No new funnel.",
        "Cash is members, not likes.",
        f"{offer} — $49/mo. Link in bio.",
    ]
    caption = (
        f"{hook}\n\nIf you want the system, not the theater: {offer} — $49/mo.\n"
        f"#buildinpublic #operators"
    )
    reel = (
        f"{hook}|Stop collecting tactics.|{promise}|"
        f"One offer. Three posts a day.|Join {offer} — $49 a month."
    )
    return {
        "hook": hook,
        "slides": slides,
        "caption": caption,
        "reel_script": reel,
        "cta": f"Join {offer} — $49/mo",
    }


_client: AsyncOpenAI | None = None


def _llm() -> AsyncOpenAI | None:
    global _client
    key = get_settings().openai_api_key
    if not key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=key)
    return _client


async def rewrite_one(title: str, body: str, cfg: dict[str, str]) -> dict[str, Any]:
    client = _llm()
    if client is None:
        return _fallback(title, cfg)
    settings = get_settings()
    user = (
        f"NICHE: {cfg.get('niche')}\nVOICE: {cfg.get('voice')}\n"
        f"ENEMY: {cfg.get('enemy')}\nPROMISE: {cfg.get('promise')}\n"
        f"OFFER: {cfg.get('offer_name')} — $49/mo\n"
        f"BULLETS: {cfg.get('offer_bullets')}\n\n"
        f"SOURCE TITLE: {title}\nSOURCE NOTES: {body[:1200]}"
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        slides = data.get("slides") or []
        if len(slides) < 7:
            fb = _fallback(title, cfg)
            slides = (slides + fb["slides"])[:7]
        return {
            "hook": str(data.get("hook") or title)[:120],
            "slides": [str(s)[:180] for s in slides[:7]],
            "caption": str(data.get("caption") or "")[:500],
            "reel_script": str(data.get("reel_script") or ""),
            "cta": str(data.get("cta") or ""),
        }
    except Exception:
        return _fallback(title, cfg)


async def rewrite_batch(items: list[tuple[str, str]], cfg: dict[str, str]) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(get_settings().rewrite_concurrency)

    async def one(title: str, body: str) -> dict[str, Any]:
        async with sem:
            return await rewrite_one(title, body, cfg)

    return await asyncio.gather(*[one(t, b) for t, b in items])
