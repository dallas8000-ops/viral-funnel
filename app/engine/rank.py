from __future__ import annotations

import math
import re

from app.engine.scout import RawHit

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if len(t) > 2}


def niche_fit(hit: RawHit, niche: str) -> float:
    if not niche:
        return 0.35
    n = _tokens(niche)
    h = _tokens(f"{hit.title} {hit.body}")
    if not n:
        return 0.35
    overlap = len(n & h) / len(n)
    return 0.25 + min(overlap, 1.0) * 0.75


def viral_score(hit: RawHit, niche: str) -> float:
    """Daily virality, not all-time popularity. Half-life ~18h."""
    vel = math.log1p(hit.velocity)
    recency = math.exp(-hit.age_hours / 18.0)
    engagement = math.log1p(hit.ups) + 0.35 * math.log1p(hit.comments)
    fit = niche_fit(hit, niche)
    return round((0.6 * vel + 0.25 * engagement * recency + 0.15 * recency) * (0.4 + fit), 4)


def rank(hits: list[RawHit], niche: str, limit: int) -> list[tuple[RawHit, float]]:
    scored = [(h, viral_score(h, niche)) for h in hits]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
