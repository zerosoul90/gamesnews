import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.community import UserBadge

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Dưới ngưỡng này thì điểm chưa nói lên gì, và một nhóm nhỏ dìm được cả game.
MIN_REVIEWS_TO_SHOW = 20


async def calculate_game_score(db: Db, game_id: str) -> dict[str, Any] | None:
    """Điểm trung bình của game, ẩn khi chưa đủ lượt đánh giá.

    Luôn trả về dict, không bao giờ None: người gọi phân biệt bằng cờ
    `is_hidden`, và khi ẩn thì `average_score` là None chứ không phải một con
    số bị đánh dấu.
    """
    pipeline: list[dict[str, Any]] = [
        {"$match": {"game_id": ObjectId(game_id)}},
        {
            "$group": {
                "_id": "$game_id",
                "average_score": {"$avg": "$score"},
                "review_count": {"$sum": 1},
            }
        },
    ]

    cursor = db.user_reviews.aggregate(pipeline)
    result = await cursor.to_list(length=1)

    count = 0
    avg = 0.0
    if result:
        stats = result[0]
        count = int(stats.get("review_count") or 0)
        avg = float(stats.get("average_score") or 0.0)

    # `PHASE-8.md`: ẩn điểm dưới 20 lượt, để chống review bombing. "Ẩn" nghĩa là
    # KHÔNG có con số trong payload — bản trước vẫn kèm `average_score` cạnh cờ
    # `is_hidden`, tức là điểm bị giấu trên giao diện nhưng ai mở tab Network
    # cũng đọc được, và bất kỳ client nào cũng vẽ nó ra được. Ẩn kiểu đó không
    # phải là ẩn.
    if count < MIN_REVIEWS_TO_SHOW:
        return {
            "average_score": None,
            "review_count": count,
            "is_hidden": True,
            "min_reviews": MIN_REVIEWS_TO_SHOW,
        }

    return {"average_score": round(avg, 1), "review_count": count, "is_hidden": False}


async def award_badge(db: Db, user_id: str, badge_type: str) -> bool:
    """
    Kiểm tra xem user đã có badge này chưa. Nếu chưa thì trao (upsert).
    """
    existing = await db.user_badges.find_one(
        {"user_id": ObjectId(user_id), "badge_type": badge_type}
    )
    if existing:
        return False

    new_badge = UserBadge(user_id=ObjectId(user_id), badge_type=badge_type)
    await db.user_badges.insert_one(new_badge.to_mongo())
    logger.info(f"Awarded badge {badge_type} to user {user_id}")
    return True
