"""Phân tầng tần suất theo dõi giá — `docs/PHASE-2.md` mục 4.

## Phép tính quota, làm lại theo số đo thật

`PHASE-2.md` dựng cả chương "Ràng buộc quyết định toàn bộ thiết kế" trên giả
định *mỗi request chỉ hỏi được một appid*. Đo thật ngày 2026-09-08:
`appdetails?filters=price_overview` nhận **tới 50 appid một lần gọi** (gửi 100
thì Steam trả về 50 và cắt phần dư **im lặng**, không báo lỗi).

Với 200 request / 5 phút mỗi IP = 57.600 request/ngày:

| Tầng | Số game | Chu kỳ | Request/ngày |
|---|---|---|---|
| Hot | 5.000 | 4 giờ | 600 |
| Ấm | 50.000 | 24 giờ | 1.000 |
| Lạnh | 130.000 | 7 ngày | ~372 |
| | | **tổng** | **~2.000 (3,5% quota)** |

Tức là **giá không phải thứ tốn quota**. Quét giá toàn bộ 185.000 game mỗi
ngày cũng chỉ hết 3.700 request (6,4%). Phân tầng vẫn cần, nhưng lý do thật
không phải "không đủ quota cho giá" mà là:

1. Đợt bồi catalog của Phase 1 tiêu 1 appid mỗi request và cần ~185.000 lượt —
   nó mới là thứ ăn hết quota, và nó dùng **chung một bucket theo IP**.
2. Phase 7 (CCU, reviews) sẽ cắn vào cùng hạn mức đó.
3. Gọi thưa với game không ai quan tâm là phép lịch sự tối thiểu với Valve, khi
   đây vốn là endpoint không chính thức.

## Tự điều tiết

Job không tự tính "còn bao nhiêu quota". Nó cứ xin token qua bucket Redis dùng
chung; hết token thì `RedisTokenBucket` ném `RateLimitedError` và job dừng lượt
đó lại. Nhờ vậy job nào chạy trước tự nhiên được ưu tiên, và không job nào phải
biết về sự tồn tại của job kia.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from app.services.catalog import games

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

Tier = Literal["hot", "warm", "cold"]

# Chu kỳ kiểm giá của từng tầng, đúng bảng trong `PHASE-2.md` mục 4.
TIER_INTERVALS: dict[Tier, dt.timedelta] = {
    "hot": dt.timedelta(hours=4),
    "warm": dt.timedelta(hours=24),
    "cold": dt.timedelta(days=7),
}

# Bài viết trong bao lâu thì coi là game còn được quan tâm.
WARM_ARTICLE_DAYS = 30
# Game mới ra mắt luôn biến động giá, kể cả khi chưa ai theo dõi.
WARM_RELEASE_DAYS = 90

INDEXES: list[IndexModel] = [
    # Truy vấn nóng nhất của job giá: lấy game tới hạn theo tầng.
    IndexModel([("price_tier", ASCENDING), ("price_checked_at", ASCENDING)], name="tier_checked"),
]


async def ensure_indexes(db: Db) -> list[str]:
    return await games(db).create_indexes(INDEXES)


async def _hot_game_ids(db: Db, extra: set[ObjectId] | None = None) -> set[ObjectId]:
    """Game thuộc tầng hot.

    Ba nguồn tín hiệu, tất cả đều là dữ liệu thật đang có trong hệ thống:

    - có người đặt cảnh báo giá (`price_alerts`) — tín hiệu mạnh nhất, người ta
      đang chờ đúng con số đó;
    - có người theo dõi (`user_follows` với `target_type = "game"`);
    - `extra`: bảng xếp hạng Steam của gian hàng VN, do job truyền vào.

    **Không** lấy từ `user_library`: đó là game người dùng đã sở hữu, và
    `CLAUDE.md` cấm báo giảm giá cho nhóm này. Theo dõi sát giá của chúng chỉ
    tốn quota mà không dùng vào việc gì.
    """
    hot: set[ObjectId] = set(extra or set())

    async for doc in db.price_alerts.find({}, {"game_id": 1}):
        if isinstance(doc.get("game_id"), ObjectId):
            hot.add(doc["game_id"])

    async for doc in db.user_follows.find({"target_type": "game"}, {"target_id": 1}):
        if isinstance(doc.get("target_id"), ObjectId):
            hot.add(doc["target_id"])

    return hot


async def _warm_game_ids(db: Db, now: dt.datetime) -> set[ObjectId]:
    """Game tầng ấm.

    `PHASE-2.md` viết "game có lượt xem trong 30 ngày", nhưng hệ thống **chưa
    đếm lượt xem** — chưa có gì ghi lại việc ai mở trang game nào. Thay bằng
    hai tín hiệu có thật và gần nghĩa:

    - có bài viết gắn vào trong 30 ngày qua (Phase 6 sinh ra dữ liệu này);
    - phát hành trong 90 ngày qua — game mới luôn biến động giá.

    Khi Phase 4 dựng xong và có số lượt xem thật, thay chỗ này chứ đừng chồng
    thêm tầng nữa.
    """
    warm: set[ObjectId] = set()

    since = (now - dt.timedelta(days=WARM_ARTICLE_DAYS)).isoformat()
    async for doc in db.articles.find(
        {"game_id": {"$ne": None}, "published_at": {"$gte": since}}, {"game_id": 1}
    ):
        game_id = doc.get("game_id")
        if isinstance(game_id, ObjectId):
            warm.add(game_id)
        elif isinstance(game_id, str) and ObjectId.is_valid(game_id):
            warm.add(ObjectId(game_id))

    released_since = (now - dt.timedelta(days=WARM_RELEASE_DAYS)).date().isoformat()
    async for doc in games(db).find(
        {"release_dates.date": {"$gte": released_since}}, {"_id": 1}
    ):
        warm.add(doc["_id"])

    return warm


async def recompute_tiers(db: Db, *, hot_extra: set[ObjectId] | None = None) -> dict[str, int]:
    """Tính lại tầng cho mọi game có bán trên Steam.

    `PHASE-2.md`: "Tầng được tính lại định kỳ, không cố định." Chạy lại được,
    và một game rơi khỏi tầng hot sẽ tự động về ấm hoặc lạnh ở lượt sau.
    """
    now = dt.datetime.now(dt.UTC)
    hot = await _hot_game_ids(db, hot_extra)
    warm = await _warm_game_ids(db, now) - hot

    only_steam = {"external_ids.steam_appid": {"$ne": None}}
    counts: dict[str, int] = {}

    for tier, ids in (("hot", hot), ("warm", warm)):
        if not ids:
            counts[tier] = 0
            continue
        result = await games(db).update_many(
            {**only_steam, "_id": {"$in": list(ids)}}, {"$set": {"price_tier": tier}}
        )
        counts[tier] = result.modified_count

    cold = await games(db).update_many(
        {**only_steam, "_id": {"$nin": list(hot | warm)}}, {"$set": {"price_tier": "cold"}}
    )
    counts["cold"] = cold.modified_count

    logger.info("tính lại tầng giá", extra=counts)
    return counts


async def due_for_check(db: Db, limit: int) -> list[dict[str, Any]]:
    """Game tới hạn kiểm giá, cũ nhất trước.

    Game chưa từng kiểm (`price_checked_at` không có) luôn tới hạn — `$lt` với
    một mốc thời gian **không khớp** document thiếu trường, nên phải nêu riêng,
    nếu không game mới nạp về sẽ không bao giờ có giá.
    """
    now = dt.datetime.now(dt.UTC)
    branches: list[dict[str, Any]] = []
    for tier, interval in TIER_INTERVALS.items():
        branches.append(
            {
                "price_tier": tier,
                "$or": [
                    {"price_checked_at": {"$lt": now - interval}},
                    {"price_checked_at": None},
                ],
            }
        )
    # Game chưa được xếp tầng lần nào cũng phải được kiểm, đừng để nó rơi ra
    # ngoài mọi nhánh chỉ vì job xếp tầng chưa chạy lượt đầu.
    branches.append({"price_tier": None})

    cursor = (
        games(db)
        .find(
            {"external_ids.steam_appid": {"$ne": None}, "$or": branches},
            {"external_ids.steam_appid": 1, "genres": 1, "price_tier": 1},
        )
        .sort([("price_checked_at", ASCENDING)])
        .limit(limit)
    )
    return [doc async for doc in cursor]
