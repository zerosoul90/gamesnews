"""Hai bảng xếp hạng của Phase 7 — `docs/PHASE-9.md` mục A1.

`compute_hotness` đã tính `game_hotness` mỗi giờ từ Phase 7, nhưng không có
endpoint nào đọc nó: một bảng xếp hạng không ai nhìn thấy được.
"""

from __future__ import annotations

from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Query

from app.core.deps import MongoDep
from app.services.metrics import HOTNESS, top_games

router = APIRouter(tags=["Hot"])

BOARDS: dict[str, str] = {
    "popular": "score_absolute",
    "rising": "score_momentum",
}


@router.get("/hot")
async def get_hot(
    db: MongoDep,
    board: Literal["popular", "rising"] = Query("popular"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Bảng "Phổ biến nhất" (`popular`) hoặc "Đang tăng mạnh" (`rising`).

    `rising` chỉ gồm game lên **ít nhất một bậc hạng**. Checkpoint Phase 7 ghi rõ
    bảng này không được để game top thường trực chiếm chỗ; chỉ lọc "momentum
    dương" thì không đủ — đo 2026-09-26 trên 59 game, đuôi bảng là PUBG
    (0.0031), Dota 2 (0.0016): dao động của trung bình cửa sổ, không phải đổi
    hạng. Momentum là chênh lệch percentile, và một bậc trong N game là
    1/(N-1) — nên ngưỡng tự nhỏ lại khi tập theo dõi lớn lên.
    """
    rows = await top_games(db, by=BOARDS[board], limit=limit)
    if board == "rising":
        ranked = await db[HOTNESS].count_documents({})
        one_rank = 1 / (ranked - 1) if ranked > 1 else 1.0
        rows = [r for r in rows if (r.get("score_momentum") or 0) >= one_rank]

    ids = [ObjectId(r["game_id"]) for r in rows if ObjectId.is_valid(r.get("game_id"))]
    games: dict[str, dict[str, Any]] = {}
    async for doc in db.games.find(
        {"_id": {"$in": ids}}, {"titles": 1, "slug": 1, "media.cover": 1}
    ):
        titles = doc.get("titles") or {}
        games[str(doc["_id"])] = {
            "title": titles.get("vi") or titles.get("primary"),
            "slug": doc.get("slug"),
            "cover_image_url": (doc.get("media") or {}).get("cover"),
        }

    prices: dict[str, dict[str, Any]] = {}
    async for doc in db.price_current.find(
        {"game_id": {"$in": ids}, "store": "steam", "region": "vn"},
        {"game_id": 1, "price_final": 1, "discount_percent": 1, "is_historical_low": 1},
    ):
        prices[str(doc["game_id"])] = {
            "price_final": doc.get("price_final"),
            "discount_percent": doc.get("discount_percent") or 0,
            "is_historical_low": bool(doc.get("is_historical_low")),
        }

    out = []
    for rank, row in enumerate(
        # Bỏ dòng trỏ tới game đã rời catalog: một thẻ không tên không ảnh
        # không giúp gì người đọc bảng xếp hạng.
        (r for r in rows if r.get("game_id") in games),
        start=1,
    ):
        game_id = row["game_id"]
        out.append(
            {
                "rank": rank,
                "game_id": game_id,
                "game_details": games[game_id],
                "ccu_now": row.get("ccu_now") or 0,
                "score_absolute": row.get("score_absolute") or 0,
                "score_momentum": row.get("score_momentum") or 0,
                "price": prices.get(game_id),
            }
        )

    computed = max((r.get("computed_at") or "" for r in rows), default="") or None
    return {"board": board, "computed_at": computed, "games": out}
