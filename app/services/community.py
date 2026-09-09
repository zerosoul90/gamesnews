import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.community import UserBadge

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def calculate_game_score(db: Db, game_id: str) -> dict[str, Any] | None:
    """
    Tính điểm trung bình của game từ collection reviews.
    Luật: Ẩn điểm (không trả về hoặc trả về cờ is_hidden=True) nếu dưới 20 lượt review.
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

    if not result:
        return {"average_score": 0.0, "review_count": 0, "is_hidden": True}

    stats = result[0]
    count = stats.get("review_count", 0)
    avg = stats.get("average_score", 0.0)

    is_hidden = count < 20

    return {"average_score": round(avg, 1), "review_count": count, "is_hidden": is_hidden}


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
