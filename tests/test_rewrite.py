from app.engine.rewrite import _fallback


def test_fallback_pack_has_seven_slides_and_cta() -> None:
    pack = _fallback("Everyone is busy and broke", {"offer_name": "The Floor", "enemy": "content theater", "promise": "clients"})
    assert len(pack["slides"]) == 7
    assert pack["cta"].startswith("Join The Floor")
    assert "|" in pack["reel_script"]
