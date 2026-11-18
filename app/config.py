from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    data_dir: Path = Path("./data")
    secret_key: str
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    upload_token_minutes: int = 15
    secure_cookies: bool = False  # set true behind HTTPS
    base_url: str | None = None  # public URL for QR codes; defaults to request base URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
