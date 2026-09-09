import datetime as dt
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

Db = AsyncIOMotorDatabase[dict[str, Any]]

async def get_active_banners(db: Db) -> list[dict[str, Any]]:
    """
    Lấy danh sách các banner quảng cáo đang trong thời gian hiệu lực
    """
    now = dt.datetime.now(dt.UTC).isoformat()

    cursor = db.banners.find({
        "start_time": {"$lte": now},
        "end_time": {"$gte": now}
    }).sort("priority", -1) # Ưu tiên số to nhất

    return await cursor.to_list(length=10)


async def get_active_giftcodes(db: Db, game_id: str) -> list[dict[str, Any]]:
    """
    Lấy danh sách giftcode chưa hết hạn của 1 game
    """
    now = dt.datetime.now(dt.UTC).isoformat()

    cursor = db.giftcodes.find({
        "game_id": ObjectId(game_id),
        "$or": [
            {"expires_at": {"$gt": now}},
            {"expires_at": None} # Không bao giờ hết hạn
        ]
    })

    return await cursor.to_list(length=50)
