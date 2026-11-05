from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    eb_app_id: str = ""
    eb_key_path: Path = Path("/secrets/eb.pem")
    eb_api_url: str = "https://api.enablebanking.com"
    eb_redirect_url: str = "https://localhost:8000/callback"
    eb_country: str = "SE"
    eb_consent_days: int = 180

    database_path: Path = Path("/data/privatebanking.db")
    frontend_dir: Path = Path(__file__).resolve().parent.parent / "static"

    sync_interval_hours: float = 6
    sync_overlap_days: int = 10
    scheduler_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
