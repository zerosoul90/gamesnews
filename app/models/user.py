from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.game import PyObjectId, mongo_document

StoreType = Literal["steam", "epic"]
TargetType = Literal["game", "series", "developer", "streamer"]
ConditionType = Literal["below_price", "discount_pct", "historical_low"]


class QuietHours(BaseModel):
    from_time: str = Field(alias="from") # "22:00"
    to_time: str = Field(alias="to")   # "07:00"

    class Config:
        populate_by_name = True


class NotificationChannels(BaseModel):
    price_alert: bool = True
    streamer_live: bool = True
    news_digest: Literal["daily", "weekly", "none"] = "daily"


class NotificationSettings(BaseModel):
    quiet_hours: QuietHours = QuietHours(from_time="22:00", to_time="07:00")
    channels: NotificationChannels = NotificationChannels()


class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    steam_id64: str | None = None
    locale: str = "vi"
    notification_settings: NotificationSettings = NotificationSettings()

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self, exclude_none=True)


class UserLibrary(BaseModel):
    """Thư viện game của user - Dùng làm bộ lọc không gửi thông báo giảm giá cho game đã có."""
    user_id: PyObjectId
    store: StoreType
    game_id: PyObjectId
    playtime_minutes: int = 0
    synced_at: str

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self)


class UserFollow(BaseModel):
    """User theo dõi game, series, dev, streamer."""
    user_id: PyObjectId
    target_type: TargetType
    target_id: PyObjectId | str # Có thể là ID MongoDB hoặc string như slug series

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self)


class PriceAlert(BaseModel):
    """Cảnh báo giá do user đặt."""
    user_id: PyObjectId
    game_id: PyObjectId
    condition: ConditionType
    value: int | None = None # VD: 200000 (below_price) hoặc 50 (discount_pct)
    currency: str = "VND"
    triggered_at: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return mongo_document(self)
