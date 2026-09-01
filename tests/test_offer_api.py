from fastapi.testclient import TestClient

from app.main import app


def test_public_offer_endpoint_returns_join_copy() -> None:
    with TestClient(app) as client:
        r = client.get("/api/offer")
        assert r.status_code == 200
        body = r.json()
        assert "offer_name" in body
        assert body["price_cents"] == 4900
        assert "promise" in body
        assert "offer_bullets" in body
