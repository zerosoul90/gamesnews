import datetime as dt
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
    """Một điểm đo. Chỉ insert, không bao giờ update.

    `ts` là `datetime` thật chứ không phải chuỗi ISO, và đó là bắt buộc chứ
    không phải sở thích: `game_metrics` là time-series collection của MongoDB,
    mà `timeField` bắt buộc phải là kiểu Date. Lưu chuỗi thì vừa không tạo
    được collection đúng kiểu, vừa làm `$dateTrunc` trong pipeline rollup
    không chạy.
    """

    ts: dt.datetime
    meta: MetricMeta
    value: int

    def to_mongo(self) -> dict[str, Any]:
        # mode mặc định (python), KHÔNG phải "json": mode json sẽ đổi `ts`
        # thành chuỗi và làm hỏng đúng điều docstring trên vừa nói.
        return self.model_dump()


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
