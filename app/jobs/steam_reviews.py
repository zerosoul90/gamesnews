"""Job đọc điểm đánh giá Steam — nguồn điểm thật duy nhất đang có.

`user_reviews` của ta có 0 bản ghi và không có giao diện nào để viết review, nên
`community_score` trên trang game luôn là `average_score: null`. Job này không
thay thế điểm cộng đồng — nó là một con số khác, từ một nhóm người khác, và trang
phải nói rõ đó là điểm của Steam.

Dùng CHUNG bucket `steam_appdetails` với job giá và job catalog: `appreviews`
nằm trên cùng host `store.steampowered.com`, mà hạn mức ở đó tính theo IP. Bucket
riêng nghĩa là ba job cùng tiêu một hạn mức mà không ai biết tổng.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig, AdapterError, RateLimitedError, RedisTokenBucket
from app.adapters.steam.adapter import DETAILS_RATE_LIMIT
from app.adapters.steam.reviews import SteamReviewsAdapter
from app.services.reviews import REVIEWS, save_review_score

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Một request một game, nên phải có trần. 60 game/lượt, 24 lượt/ngày, khoảng 1.440
# game/ngày — đủ để phủ dần catalog mà chỉ chiếm một phần nhỏ hạn mức 5 phút,
# phần còn lại để job giá và job catalog dùng.
MAX_GAMES = 60


async def sync_steam_reviews(ctx: dict[str, Any]) -> dict[str, int]:
    """Đọc điểm đánh giá cho nhóm game lâu chưa đọc nhất."""
    clients = ctx["clients"]
    db: Db = clients.db
    # Index do `core/bootstrap.ensure_storage` dựng lúc khởi động, cả ở API lẫn
    # worker — không gọi `ensure_indexes` ở đây nữa. Gọi trong job thì mỗi lượt
    # chạy lại một lượt `create_indexes`, và quan trọng hơn là nó đặt index ra
    # ngoài chỗ duy nhất liệt kê mọi index của hệ thống, đúng cái mà
    # `bootstrap.py` được dựng ra để chấm dứt.
    adapter = SteamReviewsAdapter(
        AdapterConfig(
            limiter=RedisTokenBucket(clients.redis, "steam_appdetails", DETAILS_RATE_LIMIT)
        ),
        clients.http,
    )

    targets = await _pick_games(db, MAX_GAMES)

    saved = 0
    no_reviews = 0
    failed = 0
    for game_id, appid in targets:
        try:
            summary = await adapter.fetch_summary(appid)
        except RateLimitedError:
            # Bucket cạn: dừng cả lượt thay vì đốt tiếp vào tường. Lượt sau
            # chạy lại đúng nhóm này vì thứ tự vẫn là "lâu chưa đọc nhất".
            logger.info("hết token appdetails, dừng lượt đọc review", extra={"saved": saved})
            break
        except AdapterError as exc:
            failed += 1
            logger.warning("không đọc được review", extra={"appid": appid, "error": repr(exc)})
            continue

        if summary is None:
            # Game thật chưa ai đánh giá, HOẶC appid sai — Steam trả cùng một
            # payload cho hai trường hợp đó (xem `normalize`). Không ghi gì:
            # `score: 0` sẽ hiện trên trang thành "bị chấm 0 điểm".
            no_reviews += 1
            continue

        await save_review_score(db, game_id, "steam", summary)
        saved += 1

    logger.info(
        "đồng bộ điểm review Steam",
        extra={"picked": len(targets), "saved": saved, "no_reviews": no_reviews, "failed": failed},
    )
    return {"picked": len(targets), "saved": saved, "no_reviews": no_reviews, "failed": failed}


async def _pick_games(db: Db, limit: int) -> list[tuple[Any, int]]:
    """Game chưa đọc điểm lần nào trước, rồi tới game đọc lâu nhất.

    Chưa đọc lần nào đi trước vì trang của chúng đang không có điểm nào để hiện;
    một game đã có điểm từ hôm qua thì lệch vài chục review không ai thấy.
    """
    seen: dict[Any, str] = {}
    async for doc in db[REVIEWS].find({"store": "steam"}, {"game_id": 1, "checked_at": 1}):
        seen[doc["game_id"]] = str(doc.get("checked_at") or "")

    fresh: list[tuple[Any, int]] = []
    stale: list[tuple[str, Any, int]] = []
    cursor = db.games.find(
        {"external_ids.steam_appid": {"$ne": None}},
        {"external_ids.steam_appid": 1},
    )
    async for doc in cursor:
        appid = (doc.get("external_ids") or {}).get("steam_appid")
        if appid is None:
            continue
        game_id = doc["_id"]
        if game_id in seen:
            stale.append((seen[game_id], game_id, int(appid)))
        else:
            fresh.append((game_id, int(appid)))
            if len(fresh) >= limit:
                return fresh

    stale.sort(key=lambda row: row[0])
    return fresh + [(game_id, appid) for _, game_id, appid in stale[: limit - len(fresh)]]
