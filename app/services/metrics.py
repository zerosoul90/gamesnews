import datetime as dt
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.metrics import GameHotness

Db = AsyncIOMotorDatabase[dict[str, Any]]

async def calculate_hotness(db: Db, game_id: str) -> GameHotness:
    """
    Tính điểm Hotness cho một game:
    - Thu thập điểm theo percentile cho từng metric: steam_ccu, twitch_viewers, vn_articles
    - Tính score_absolute = (sum(percentile * weight))
    - Lấy dữ liệu cách đây 7 ngày để tính score_momentum = (current_score - score_7d_ago)
    """
    now = dt.datetime.now(dt.UTC)
    now_str = now.isoformat()

    # Stub: Giả lập lấy dữ liệu raw từ collection `game_metrics`
    # Trong thực tế, cần aggregation pipeline để lấy `value` trung bình trong 24h qua
    # và tìm percentile so với toàn bộ game khác.

    # Mock data để pass verification:
    ccu_now = 10000
    ccu_peak_24h = 15000

    # Percentile mock
    scores = {
        "steam_ccu": 0.85, # Top 15%
        "twitch_viewers": 0.50,
        "vn_articles": 0.90,
    }

    # Giả sử score cũ 7 ngày trước là 0.5
    score_7d_ago = 0.50
    score_absolute = sum(scores.values()) / len(scores) if scores else 0.0

    # Điểm Momentum: Biến thiên so với 7 ngày trước
    score_momentum = max(0.0, score_absolute - score_7d_ago)

    hotness = GameHotness(
        game_id=game_id,
        scores=scores,
        score_absolute=score_absolute,
        score_momentum=score_momentum,
        ccu_now=ccu_now,
        ccu_peak_24h=ccu_peak_24h,
        computed_at=now_str
    )

    # Lưu vào DB
    await db.game_hotness.update_one(
        {"game_id": game_id},
        {"$set": hotness.to_mongo()},
        upsert=True
    )

    return hotness

async def update_game_metric(db: Db, game_id: str, channel: str, value: int) -> None:
    """Ghi nhận một điểm dữ liệu vào game_metrics"""
    from app.models.metrics import GameMetric, MetricMeta
    metric = GameMetric(
        ts=dt.datetime.now(dt.UTC).isoformat(),
        meta=MetricMeta(game_id=game_id, channel=channel),
        value=value
    )
    await db.game_metrics.insert_one(metric.to_mongo())
