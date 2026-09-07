"""Cấu hình đọc toàn bộ từ biến môi trường. Không hardcode giá trị nghiệp vụ."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_port: int = 8000
    log_level: str = "INFO"

    # --- Kho dữ liệu ---
    mongo_uri: str = "mongodb://mongo:27017"
    mongo_db: str = "gamesnews"
    redis_url: str = "redis://redis:6379/0"
    meili_url: str = "http://meilisearch:7700"
    meili_master_key: SecretStr = SecretStr("")
    qdrant_url: str = "http://qdrant:6333"

    # Timeout cho mọi lần ping phụ thuộc trong /health, tính bằng giây.
    health_timeout_seconds: float = Field(default=2.0, gt=0)

    # --- Key ngoài. Phase 0 chưa gọi API nào nên để trống vẫn chạy được. ---
    steam_api_key: SecretStr = SecretStr("")
    twitch_client_id: str = ""
    twitch_client_secret: SecretStr = SecretStr("")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
