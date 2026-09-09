import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig, RedisTokenBucket
from app.adapters.steam.adapter import DETAILS_RATE_LIMIT, SteamCatalogAdapter
from app.core.config import get_settings
from app.models.price import PriceCurrent
from app.services.pricing import mark_region_locked, record_prices

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Mỗi lượt quét lấy 50 appid
BATCH_SIZE = 50


def _adapter(ctx: dict[str, Any]) -> SteamCatalogAdapter:
    clients = ctx["clients"]
    settings = get_settings()
    # Dùng chung bucket steam_appdetails với job catalog Phase 1
    return SteamCatalogAdapter(
        AdapterConfig(
            limiter=RedisTokenBucket(clients.redis, "steam_appdetails", DETAILS_RATE_LIMIT)
        ),
        clients.http,
        api_key=settings.steam_api_key.get_secret_value(),
    )


async def sync_steam_prices(ctx: dict[str, Any]) -> dict[str, int]:
    """Lấy giá Steam cho một lô game."""
    db: Db = ctx["clients"].db
    adapter = _adapter(ctx)

    # 1. Tìm 50 game cần check. CHƯA có phân tầng hot/ấm/lạnh thật — hiện chỉ
    #    ưu tiên game chưa check, hoặc check lâu nhất.
    cursor = (
        db.games.find(
            {"external_ids.steam_appid": {"$ne": None}, "type": {"$in": ["game", "dlc"]}},
            {"external_ids.steam_appid": 1, "genres": 1, "price_checked_at": 1},
        )
        .sort([("price_checked_at", 1)])
        .limit(BATCH_SIZE)
    )

    games = await cursor.to_list(None)
    if not games:
        return {"fetched": 0}

    appids = [int(g["external_ids"]["steam_appid"]) for g in games]
    game_map = {int(g["external_ids"]["steam_appid"]): g for g in games}

    # 2. Đánh dấu thời điểm check để lượt sau không bị trùng ngay, kể cả khi API lỗi
    now = dt.datetime.now(dt.UTC)
    await db.games.update_many(
        {"_id": {"$in": [g["_id"] for g in games]}}, {"$set": {"price_checked_at": now}}
    )

    # 3. Gọi API
    prices_data = await adapter.prices(appids)

    current_prices = []
    locked_game_ids = []

    for appid, pdata in prices_data.items():
        game = game_map[appid]
        genres = game.get("genres", [])

        # Kiểm tra F2P / Khóa vùng khi không có price_overview
        if not pdata or "price_overview" not in pdata:
            if "free-to-play" not in genres:
                locked_game_ids.append(game["_id"])
            else:
                # Ghi nhận game F2P với giá 0
                current_prices.append(
                    PriceCurrent(
                        game_id=game["_id"],
                        store="steam",
                        price_initial=0,
                        price_final=0,
                        discount_percent=0,
                        is_free_promo=False,
                    )
                )
            continue

        overview = pdata["price_overview"]
        initial = int(overview.get("initial", 0)) // 100
        final = int(overview.get("final", 0)) // 100
        discount = int(overview.get("discount_percent", 0))

        current_prices.append(
            PriceCurrent(
                game_id=game["_id"],
                store="steam",
                price_initial=initial,
                price_final=final,
                discount_percent=discount,
            )
        )

    # Ghi nhận giá
    res = await record_prices(db, current_prices)
    if locked_game_ids:
        await mark_region_locked(db, locked_game_ids)

    logger.info(
        "steam_pricing: cập nhật lô",
        extra={
            "batch": len(appids),
            "updated": res["updated"],
            "history": res["history_added"],
            "locked": len(locked_game_ids),
        },
    )
    return {
        "batch": len(appids),
        "updated": res["updated"],
        "history": res["history_added"],
        "locked": len(locked_game_ids),
    }
