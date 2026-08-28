from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ASSET_DIR = DATA_DIR / "assets"
DB_PATH = DATA_DIR / "engine.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_secret: str = "change-me"
    public_url: str = "http://127.0.0.1:8787"
    timezone: str = "America/New_York"
    post_hours: str = "8,12,18"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    rewrite_concurrency: int = 8
    scout_concurrency: int = 24
    render_workers: int = 4
    inventory_days: int = 7
    scout_limit: int = 80

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_price_cents: int = 4900
    mrr_target_cents: int = 500_000

    meta_page_access_token: str = ""
    meta_ig_user_id: str = ""

    discord_invite_url: str = ""

    @property
    def post_hour_list(self) -> list[int]:
        return [int(h.strip()) for h in self.post_hours.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
