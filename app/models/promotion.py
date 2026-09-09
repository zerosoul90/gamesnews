import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from app.models.game import PyObjectId, mongo_document


class Giftcode(BaseModel):
    """Giftcode game"""
    game_id: PyObjectId
    code: str
    description: str | None = None
    expires_at: str | None = None
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self)


class Banner(BaseModel):
    """Lịch chạy Banner cho Mobile App"""
    image_url: str
    link_url: str
    priority: int = 0
    start_time: str
    end_time: str

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self)
