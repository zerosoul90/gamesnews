from typing import Any, Literal

from pydantic import BaseModel, Field


class MetricMeta(BaseModel):
    game_id: str
    channel: Literal[
        "steam_ccu",
        "twitch_viewers",
        "youtube_videos",
        "steam_reviews_new",
        "vn_articles",
        "internal_views",
        "internal_wishlist",
    ]


class GameMetric(BaseModel):
    """
    Time-series model để ghi log metrics.
    Lưu ý: Không update, chỉ insert.
    """
    ts: str # ISODate string
    meta: MetricMeta
    value: int

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GameHotness(BaseModel):
    """
    Điểm số đã được tính toán (chuẩn hoá percentile và tổng hợp)
    Tương đương collection `game_hotness`
    """
    game_id: str
    scores: dict[str, float] = Field(default_factory=dict)
    score_absolute: float = 0.0
    score_momentum: float = 0.0
    ccu_now: int = 0
    ccu_peak_24h: int = 0
    ccu_peak_all_time: int = 0
    ccu_peak_all_time_date: str | None = None
    computed_at: str | None = None

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
