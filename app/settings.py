from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_allowed_user_ids: str = ""

    ip_public: str = ""
    port_onu: int = 12500
    comment_firewall: str = "1. REMOT ONU"

    mikrotik_host: str = ""
    mikrotik_username: str = ""
    mikrotik_password: str = ""
    mikrotik_port: int = 8728

    nuxbill_api_url: str
    nuxbill_username: str
    nuxbill_password: str

    nuxbill_activate_using: str = "zero"

    bot_rate_limit_max: int = 5
    bot_rate_limit_window_sec: int = 10

    audit_db_path: str = "./audit.db"
    log_level: str = "INFO"

    def allowed_user_ids(self) -> set[int]:
        raw = (self.telegram_allowed_user_ids or "").strip()
        if not raw:
            return set()
        items = raw.replace("\n", ",").replace(" ", ",").split(",")
        out: set[int] = set()
        for item in items:
            v = item.strip()
            if not v:
                continue
            if not v.isdigit():
                continue
            out.add(int(v))
        return out

    def onu_remote_enabled(self) -> bool:
        if not self.ip_public.strip():
            return False
        if self.port_onu <= 0:
            return False
        if not self.comment_firewall.strip():
            return False
        if not self.mikrotik_host.strip():
            return False
        if not self.mikrotik_username.strip():
            return False
        if not self.mikrotik_password.strip():
            return False
        if self.mikrotik_port <= 0:
            return False
        return True


def load_settings() -> Settings:
    return Settings()
