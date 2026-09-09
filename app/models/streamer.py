from typing import Any, Literal

from pydantic import BaseModel


class Streamer(BaseModel):
    """
    Thông tin streamer được lưu trữ
    """
    platform: Literal["twitch", "youtube", "tiktok"]
    channel_id: str
    display_name: str
    language: str = "vi"
    is_live: bool = False
    current_game_id: str | None = None
    viewers: int = 0
    websub_expires_at: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
