from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    database_path: Path = Field(default=Path("./data/library.db"))
    download_dir: Path = Field(default=Path("./downloads"))
    max_file_mb: int = Field(default=50, ge=1, le=2000)
    download_timeout_sec: int = Field(default=120, ge=5)
    http_head_timeout_sec: int = Field(default=15, ge=2)
    allowed_hosts: str = ""
    admin_host: str = "0.0.0.0"
    admin_port: int = Field(default=8080, ge=1, le=65535)
    admin_secret: str = ""

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024

    @property
    def allowed_host_set(self) -> frozenset[str]:
        parts = [h.strip().lower() for h in self.allowed_hosts.split(",") if h.strip()]
        return frozenset(parts)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
