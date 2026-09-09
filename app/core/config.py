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

    # --- Admin ---
    #
    # Phase 3 mới có auth thật. Tới lúc đó, một token tĩnh là thứ duy nhất
    # ngăn người lạ sửa catalog. Để trống thì `/admin` từ chối mọi request —
    # mở sẵn một trang sửa entity không mật khẩu nguy hiểm hơn nhiều so với
    # việc admin tạm thời không dùng được.
    admin_token: SecretStr = SecretStr("")

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr("changeme_for_production")
    frontend_url: str = "http://localhost:3000"

    # --- Key ngoài. Phase 0 chưa gọi API nào nên để trống vẫn chạy được. ---
    steam_api_key: SecretStr = SecretStr("")
    twitch_client_id: str = ""
    twitch_client_secret: SecretStr = SecretStr("")
    # Chuỗi bí mật ta tự đặt khi đăng ký EventSub, dùng để kiểm chữ ký HMAC của
    # mỗi notification. Để trống thì webhook Twitch từ chối phục vụ — thà không
    # nhận còn hơn nhận rồi tin vào một chữ ký ai cũng ký được.
    twitch_webhook_secret: SecretStr = SecretStr("")
    # Bí mật ta gửi kèm khi đăng ký WebSub, dùng kiểm `X-Hub-Signature` của
    # mỗi notification. Để trống thì endpoint YouTube từ chối phục vụ.
    youtube_websub_secret: SecretStr = SecretStr("")

    # --- Firebase Cloud Messaging (push) ---
    #
    # Ba giá trị này lấy từ file JSON service account của Firebase. Thiếu bất
    # kỳ giá trị nào thì `send_push_notification` ghi log lỗi và trả về 0 —
    # KHÔNG im lặng coi như đã gửi.
    fcm_project_id: str = ""
    fcm_client_email: str = ""
    fcm_private_key: SecretStr = SecretStr("")
    # URL công khai của chính ta, để hub biết đẩy notification về đâu.
    public_base_url: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    youtube_api_key: SecretStr = SecretStr("")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
