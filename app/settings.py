from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str
    telegram_webhook_secret: str

    nuxbill_api_url: str
    nuxbill_username: str
    nuxbill_password: str

    nuxbill_activate_using: str = "zero"

    bot_rate_limit_max: int = 5
    bot_rate_limit_window_sec: int = 10

    audit_db_path: str = "./audit.db"
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()
