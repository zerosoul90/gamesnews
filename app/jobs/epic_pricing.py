"""Game miễn phí hàng tuần trên Epic — nguồn store thứ hai sau Steam.

`EpicFreeGamesAdapter` có trong repo từ trước nhưng **không job nào gọi nó**, nên
`price_current` chỉ có đúng một store: `distinct("store")` trả `["steam"]`. Hệ
quả thấy được: `/free-games` luôn rỗng vì nó đọc `price_current.is_free_promo`,
và bảng so sánh giá trên trang game không bao giờ có hơn một dòng.

Ghi qua `record_prices` chứ không tự upsert: chỉ hàm đó mới biết tính
`lowest_ever`, `observations`, cờ `is_historical_low` và đẩy `price_history` khi
giá thật sự đổi. Tự viết upsert ở đây là sinh ra một nhánh thứ hai tính những
thứ đó theo cách khác.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig, AdapterError, RateLimit, RedisTokenBucket
from app.adapters.epic.adapter import EpicFreeGamesAdapter
from app.models.price import PriceCurrent
from app.services.entity_matcher import match_by_alias
from app.services.pricing import record_prices

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Một request cho cả danh sách, mỗi giờ một lượt. Hạn mức đặt rộng rãi vì
# endpoint này là file tĩnh sau CDN của Epic, không phải API tính quota.
EPIC_RATE = RateLimit(capacity=30, per_seconds=60.0)

# Tặng miễn phí thì giá cuối bằng 0 và giảm 100%, không phụ thuộc Epic trả gì.
FREE_DISCOUNT_PERCENT = 100


async def sync_epic_free_games(ctx: dict[str, Any]) -> dict[str, int]:
    """Ghi nhận các game đang được Epic tặng miễn phí."""
    clients = ctx["clients"]
    db: Db = clients.db

    adapter = EpicFreeGamesAdapter(
        AdapterConfig(limiter=RedisTokenBucket(clients.redis, "epic_free", EPIC_RATE)),
        clients.http,
    )

    try:
        offers = await adapter.fetch_free_games()
    except AdapterError as exc:
        logger.warning("không lấy được free games Epic", extra={"error": repr(exc)})
        return {"offers": 0, "matched": 0, "unmatched": 0, "updated": 0, "history": 0}

    now = dt.datetime.now(dt.UTC).isoformat()
    prices: list[PriceCurrent] = []
    unmatched: list[str] = []

    for offer in offers:
        title = (offer.get("title") or "").strip()
        if not title:
            continue

        # Khớp theo TÊN, không theo slug: slug Epic không tra được sang catalog
        # của ta (catalog dựng từ Steam), và với Astral Ascent nó còn là GUID.
        match = await match_by_alias(db, title)
        if match is None:
            # Bỏ qua nhưng ĐẾM và ghi log. Nguyên nhân thường là độ phủ catalog
            # chứ không phải lỗi khớp: Astral Ascent nằm trong `steam_apps`
            # (185.231 app chờ) mà chưa tới lượt `sync_steam_details`. Im lặng
            # bỏ thì không ai biết danh sách free đang thiếu game.
            unmatched.append(title)
            continue

        price_initial = offer.get("price_initial")
        prices.append(
            PriceCurrent(
                game_id=match.game_id,
                store="epic",
                currency=offer.get("currency") or "VND",
                # Giá gốc để người đọc thấy mình tiết kiệm bao nhiêu. Thiếu thì
                # để 0 chứ không bỏ qua cả game — bản thân việc nó đang free mới
                # là thông tin chính.
                price_initial=int(price_initial) if price_initial is not None else 0,
                price_final=0,
                discount_percent=FREE_DISCOUNT_PERCENT,
                is_free_promo=True,
                promo_ends_at=offer.get("promo_ends_at"),
                url=offer.get("url"),
                checked_at=now,
            )
        )

        await _link_epic_ids(db, match.game_id, offer)

    result = await record_prices(db, prices, http=clients.http)

    logger.info(
        "đồng bộ free games Epic",
        extra={
            "offers": len(offers),
            "matched": len(prices),
            "unmatched": len(unmatched),
            # Tên cụ thể, không chỉ số đếm: cần biết game nào thiếu để tra.
            "unmatched_titles": unmatched,
        },
    )
    return {
        "offers": len(offers),
        "matched": len(prices),
        "unmatched": len(unmatched),
        "updated": result["updated"],
        "history": result["history_added"],
    }


async def _link_epic_ids(db: Db, game_id: Any, offer: dict[str, Any]) -> None:
    """Điền `external_ids.epic_slug` và `epic_namespace`.

    Hai field này có trong model từ đầu mà chưa nguồn nào điền. Có chúng thì lần
    sau không cần khớp lại theo tên — và `entity_matcher.match_by_store_link`
    tra được entity từ một link Epic trong bài viết.

    Chỉ `$set` hai field, không đi qua `upsert_game`: ta không có một `Game` đầy
    đủ ở đây, và ghi cả entity từ dữ liệu Epic sẽ đè mất dữ liệu Steam vốn giàu
    hơn (genres, developers, cấu hình).
    """
    updates = {
        key: value
        for key, value in (
            ("external_ids.epic_slug", offer.get("slug")),
            ("external_ids.epic_namespace", offer.get("namespace")),
        )
        if value
    }
    if updates:
        await db.games.update_one({"_id": game_id}, {"$set": updates})
