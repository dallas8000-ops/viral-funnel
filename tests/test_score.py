from app.engine.rank import viral_score
from app.engine.scout import RawHit
from app.engine.scoreboard import members_needed, verdict


def test_members_needed_is_103() -> None:
    assert members_needed() == 103


def test_day30_miss_is_failed() -> None:
    v = verdict(30, 20)
    assert v["status"] == "FAILED"


def test_day30_hit() -> None:
    v = verdict(30, 103)
    assert v["status"] == "HIT"


def test_velocity_beats_stale_volume() -> None:
    hot = RawHit("reddit", "", "close more retainers this week", "", ups=120, comments=40, created_ts=__import__("time").time() - 3600)
    stale = RawHit("reddit", "", "close more retainers this week old", "", ups=8000, comments=400, created_ts=__import__("time").time() - 86400 * 20)
    niche = "retainers operators"
    assert viral_score(hot, niche) > viral_score(stale, niche)
