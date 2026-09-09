import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DeleteMany, InsertOne

from app.adapters.base import AdapterConfig, SlidingWindowRateLimiter
from app.adapters.steam.user import PrivateProfileError, SteamUserAdapter
from app.core.config import get_settings
from app.models.game import PyObjectId
from app.models.user import UserLibrary

logger = logging.getLogger(__name__)


def _steam_user_adapter(http) -> SteamUserAdapter:
    settings = get_settings()
    # Rate limit lỏng lẻo hơn cho API người dùng
    limiter = SlidingWindowRateLimiter(limit=10, window_size=1.0)
    return SteamUserAdapter(AdapterConfig(limiter=limiter), http, api_key=settings.steam_api_key.get_secret_value())


async def sync_steam_library(db: AsyncIOMotorDatabase[dict[str, Any]], http: Any, user_id: PyObjectId, steam_id64: str) -> dict[str, Any]:
    """
    Đồng bộ thư viện game từ Steam. 
    Bắn PrivateProfileError nếu profile đóng.
    """
    adapter = _steam_user_adapter(http)
    
    # 1. Fetch data
    games = await adapter.get_owned_games(steam_id64)
    # Chưa xử lý wishlist ở đây vì phức tạp map ID
    
    if not games:
        return {"synced": 0, "skipped": 0}

    # 2. Map appid -> game_id
    appids = [g["appid"] for g in games]
    cursor = db.games.find({"external_ids.steam_appid": {"$in": appids}}, {"external_ids.steam_appid": 1})
    
    game_map = {}
    async for doc in cursor:
        game_map[doc["external_ids"]["steam_appid"]] = doc["_id"]

    now = dt.datetime.now(dt.UTC).isoformat()
    
    # 3. Chuẩn bị bulk operations
    new_records = []
    skipped = 0
    
    for g in games:
        appid = g["appid"]
        game_id = game_map.get(appid)
        
        if not game_id:
            # Game chưa có trong catalog của ta -> bỏ qua
            skipped += 1
            continue
            
        new_records.append(
            UserLibrary(
                user_id=user_id,
                store="steam",
                game_id=game_id,
                playtime_minutes=g.get("playtime_forever", 0),
                synced_at=now,
            ).to_mongo()
        )

    # 4. Xoá thư viện steam cũ của user này và chèn cái mới (upsert toàn khối)
    ops = [DeleteMany({"user_id": user_id, "store": "steam"})]
    if new_records:
        ops.append(InsertOne(r) for r in new_records) # InsertMany tốt hơn
        
    await db.user_library.delete_many({"user_id": user_id, "store": "steam"})
    if new_records:
        await db.user_library.insert_many(new_records)
        
    logger.info("Đồng bộ xong thư viện", extra={"user_id": str(user_id), "synced": len(new_records), "skipped": skipped})
    return {"synced": len(new_records), "skipped": skipped}


async def delete_library(db: AsyncIOMotorDatabase[dict[str, Any]], user_id: PyObjectId) -> int:
    """Xóa toàn bộ thư viện để tuân thủ quyền riêng tư."""
    result = await db.user_library.delete_many({"user_id": user_id})
    return result.deleted_count
