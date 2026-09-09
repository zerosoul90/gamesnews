"""Cấu hình đọc toàn bộ từ biến môi trường. Không hardcode giá trị nghiệp vụ."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Giá trị mặc định của `jwt_secret`. Nằm trong mã nguồn nên ai đọc repo cũng
# biết — dùng nó ở môi trường thật thì bất kỳ ai cũng ký được token hợp lệ cho
# bất kỳ tài khoản nào. Xem `_chan_secret_mac_dinh`.
# S105: ruff thấy một chuỗi trông như mật khẩu và cảnh báo — đúng bản chất,
# nhưng đây chính là giá trị canh gác để TỪ CHỐI, không phải một secret đang
# dùng. Giấu nó đi thì mất luôn chốt chặn.
DEFAULT_JWT_SECRET = "changeme_for_production"  # noqa: S105


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

    # Timeout HTTP của worker, tính bằng giây. Phải rộng hơn hẳn
    # `health_timeout_seconds`: một /health chậm 2 giây là hỏng, còn một job
    # đẩy batch nghìn document sang Meilisearch hay gọi Steam mất vài giây là
    # bình thường. Dùng chung trần của /health thì job đứt giữa chừng.
    job_timeout_seconds: float = Field(default=30.0, gt=0)

    # --- Admin ---
    #
    # Phase 3 mới có auth thật. Tới lúc đó, một token tĩnh là thứ duy nhất
    # ngăn người lạ sửa catalog. Để trống thì `/admin` từ chối mọi request —
    # mở sẵn một trang sửa entity không mật khẩu nguy hiểm hơn nhiều so với
    # việc admin tạm thời không dùng được.
    admin_token: SecretStr = SecretStr("")

    # --- Auth ---
    jwt_secret: SecretStr = SecretStr(DEFAULT_JWT_SECRET)
    frontend_url: str = "http://localhost:3000"

    # Origin được phép gọi API từ trình duyệt, phân tách bằng dấu phẩy.
    # Mặc định là hai cổng dev của Angular (`ng serve` và bản SSR).
    cors_origins: str = "http://localhost:4200,http://localhost:4000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

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

    @model_validator(mode="after")
    def _chan_secret_mac_dinh(self) -> "Settings":
        """Ngoài `dev` thì không được chạy với `jwt_secret` mặc định.

        `jwt_secret` ký session token của người dùng. Giá trị mặc định nằm ngay
        trong mã nguồn, nên deploy mà quên đặt biến này thì bất kỳ ai đọc repo
        cũng ký được token hợp lệ cho bất kỳ tài khoản nào — kể cả admin.

        Chết lúc khởi động là có chủ ý. Một biến thiếu thì hỏng ngay và hỏng ồn
        ào, còn hơn chạy ngon lành suốt nhiều tháng với auth chỉ là hình thức:
        loại lỗi này không có triệu chứng nào cho tới lúc đã bị lợi dụng.

        Chặn cả `staging` chứ không riêng `prod`: staging cũng là máy thật, có
        dữ liệu thật và mở ra mạng.
        """
        if self.app_env != "dev" and self.jwt_secret.get_secret_value() == DEFAULT_JWT_SECRET:
            raise ValueError(
                f"JWT_SECRET còn là giá trị mặc định trong khi APP_ENV={self.app_env}. "
                "Đặt một giá trị riêng, sinh bằng: openssl rand -base64 32"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
