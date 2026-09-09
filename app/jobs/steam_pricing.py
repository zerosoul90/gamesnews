import datetime as dt
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig, RateLimitedError, RedisTokenBucket
from app.adapters.steam.adapter import DETAILS_RATE_LIMIT, SteamCatalogAdapter
from app.adapters.steam.charts import SteamChartsAdapter
from app.core.config import get_settings
from app.models.price import PriceCurrent
from app.services import price_tier
from app.services.pricing import mark_region_locked, record_prices

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Trần thật của Steam: `filters=price_overview` nhận tối đa 50 appid, gửi hơn
# thì phần dư bị cắt IM LẶNG. Đo tay 2026-09-08.
BATCH_SIZE = 50

# Số lô mỗi lượt job. 20 lô = 1.000 game = 20 request, tức 10% hạn mức 5 phút —
# đủ nhanh để tầng hot xong trong một lượt, mà vẫn chừa quota cho job bồi
# catalog đang chạy song song trên cùng bucket.
MAX_BATCHES = 20


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
    """Lấy giá Steam cho các game tới hạn, theo tầng.

    Dừng sớm khi bucket dùng chung cạn token: job bồi catalog và job giá tranh
    nhau đúng một hạn mức tính theo IP, nên thà lượt này lấy ít còn hơn làm job
    kia chết đói.
    """
    db: Db = ctx["clients"].db
    adapter = _adapter(ctx)

    tally = {"batches": 0, "checked": 0, "updated": 0, "history": 0, "locked": 0}

    for _ in range(MAX_BATCHES):
        games = await price_tier.due_for_check(db, BATCH_SIZE)
        if not games:
            break
        try:
            result = await _check_batch(db, adapter, games)
        except RateLimitedError as exc:
            logger.info(
                "bucket steam cạn, dừng lượt giá tại đây",
                extra={"batches_done": tally["batches"], "error": str(exc)},
            )
            break
        tally["batches"] += 1
        for key in ("checked", "updated", "history", "locked"):
            tally[key] += result[key]

    logger.info("steam_pricing: xong lượt", extra=tally)
    return tally


async def _check_batch(
    db: Db, adapter: SteamCatalogAdapter, games: list[dict[str, Any]]
) -> dict[str, int]:
    appids = [int(g["external_ids"]["steam_appid"]) for g in games]
    game_map = {int(g["external_ids"]["steam_appid"]): g for g in games}

    # Đánh dấu đã kiểm TRƯỚC khi gọi API: lượt sau không lấy lại đúng lô này
    # kể cả khi Steam lỗi. Mất một chu kỳ với vài game còn hơn kẹt vĩnh viễn ở
    # cùng một lô hỏng và không game nào khác được kiểm.
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

    return {
        "checked": len(appids),
        "updated": res["updated"],
        "history": res["history_added"],
        "locked": len(locked_game_ids),
    }


async def recompute_price_tiers(ctx: dict[str, Any]) -> dict[str, int]:
    """Job xếp lại tầng. Chạy ngày một lần là đủ — tầng đổi chậm.

    Bảng xếp hạng Steam của gian hàng VN được nhập vào tầng hot: game đang bán
    chạy thì nhiều người hỏi giá nhất, dù chưa ai trong hệ thống theo dõi nó.
    """
    db: Db = ctx["clients"].db
    await price_tier.ensure_indexes(db)

    hot_extra: set[ObjectId] = set()
    try:
        charts = SteamChartsAdapter(
            ctx["clients"].http, get_settings().steam_api_key.get_secret_value()
        )
        appids = await charts.get_top_sellers_vn()
        async for doc in db.games.find(
            {"external_ids.steam_appid": {"$in": appids}}, {"_id": 1}
        ):
            hot_extra.add(doc["_id"])
    except Exception as exc:
        # Bảng xếp hạng là gia vị, không phải nguyên liệu chính. Hỏng thì tầng
        # hot vẫn còn hai nguồn kia.
        logger.warning("không lấy được bảng xếp hạng Steam", extra={"error": repr(exc)})

    return await price_tier.recompute_tiers(db, hot_extra=hot_extra)
