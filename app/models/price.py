from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.game import PyObjectId

StoreType = Literal["steam", "epic", "gog", "cheapshark", "app_store", "google_play"]


class PriceCurrent(BaseModel):
    """Giá hiện tại của một game tại một store. Update (upsert) liên tục."""

    game_id: PyObjectId
    store: StoreType
    region: str = "vn"
    currency: str = "VND"

    price_initial: int
    price_final: int
    discount_percent: int

    is_free_promo: bool = False
    promo_ends_at: str | None = None

    lowest_ever: int | None = None
    lowest_ever_date: str | None = None
    is_historical_low: bool = False

    url: str | None = None
    checked_at: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json", exclude_none=True)
        doc["game_id"] = self.game_id
        return doc


class PriceHistory(BaseModel):
    """Lịch sử giá, chỉ append khi có thay đổi."""

    game_id: PyObjectId
    store: StoreType
    region: str = "vn"
    price_final: int
    discount_percent: int
    changed_at: str

    def to_mongo(self) -> dict[str, Any]:
        doc = self.model_dump(mode="json")
        doc["game_id"] = self.game_id
        return doc
