import datetime as dt
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.serialization import jsonify_docs
from app.models.game import PyObjectId

router = APIRouter(tags=["Prices & Deals"])

# "Đáng mua" theo `PHASE-2.md`: đang ở đáy lịch sử, HOẶC giảm đủ sâu để không
# phải đợt hạ giá lấy lệ. Một con số duy nhất, đặt ở một chỗ, để API lọc và
# API gắn cờ không bao giờ nói hai điều khác nhau về cùng một game.
WORTH_BUYING_DISCOUNT = 50


def _is_worth_buying(deal: dict[str, Any]) -> bool:
    return bool(deal.get("is_historical_low")) or int(deal.get("discount_percent") or 0) >= (
        WORTH_BUYING_DISCOUNT
    )


async def _attach_games(
    db: AsyncIOMotorDatabase[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Gắn tên, slug và ảnh bìa vào từng dòng giá.

    Không có bước này thì `/deals` chỉ trả về `game_id` và một con số, và trang
    deal của web hiển thị đúng như nó nhận được: hai chục thẻ "Unknown Game"
    với ảnh placeholder. Người dùng không mua một cái `ObjectId`.

    MỘT truy vấn cho cả lô, không phải một truy vấn mỗi thẻ: danh sách 100 deal
    mà tra từng cái là 100 lượt đi Mongo cho một lần tải trang.
    """
    ids = [row["game_id"] for row in rows if isinstance(row.get("game_id"), ObjectId)]
    if not ids:
        return jsonify_docs(rows)

    lookup: dict[ObjectId, dict[str, Any]] = {}
    cursor = db.games.find({"_id": {"$in": ids}}, {"titles": 1, "slug": 1, "media.cover": 1})
    async for doc in cursor:
        titles = doc.get("titles") or {}
        lookup[doc["_id"]] = {
            # Tên tiếng Việt trước: trang này để người Việt đọc.
            "title": titles.get("vi") or titles.get("primary"),
            "slug": doc.get("slug"),
            "cover_image_url": (doc.get("media") or {}).get("cover"),
        }

    out = jsonify_docs(rows)
    for row, original in zip(out, rows, strict=True):
        # `None` chứ không phải `{}`: entity giá trỏ tới một game không còn
        # trong catalog là một sự cố dữ liệu, và client phải phân biệt được nó
        # với "game có thật nhưng chưa có ảnh bìa".
        game_id = original.get("game_id")
        row["game_details"] = lookup.get(game_id) if isinstance(game_id, ObjectId) else None
    return out


@router.get("/games/{game_id}/prices")
async def get_prices(request: Request, game_id: PyObjectId) -> dict[str, Any]:
    """Giá hiện tại mọi store, mọi region đang theo dõi."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    game = await db.games.find_one({"_id": game_id})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    cursor = db.price_current.find({"game_id": game_id}, {"_id": 0})
    prices = await cursor.to_list(None)
    return {"prices": jsonify_docs(prices)}


@router.get("/games/{game_id}/price-history")
async def get_price_history(
    request: Request, game_id: PyObjectId, days: int = Query(30, ge=1, le=365)
) -> dict[str, Any]:
    """Dữ liệu vẽ biểu đồ lịch sử giá."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).isoformat()

    cursor = db.price_history.find(
        {"game_id": game_id, "changed_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("changed_at", 1)

    history = await cursor.to_list(None)
    return {"history": jsonify_docs(history)}


@router.get("/deals")
async def get_deals(
    request: Request,
    limit: int = Query(20, le=100),
    filter_by: Literal["historical_low", "worth_buying"] | None = Query(
        None, description="Lọc theo chất lượng deal"
    ),
) -> dict[str, Any]:
    """Danh sách deal sắp xếp theo chất lượng deal.

    `filter_by` khai bằng `Literal` chứ không phải `str`: gõ sai một chữ thì
    nhận 422 ngay, thay vì nhận về **toàn bộ** deal như thể không lọc gì — cái
    sai im lặng khó chịu nhất của một tham số lọc.
    """
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    query: dict[str, Any] = {"discount_percent": {"$gt": 0}}

    if filter_by == "historical_low":
        query["is_historical_low"] = True
    elif filter_by == "worth_buying":
        query["$or"] = [
            {"is_historical_low": True},
            {"discount_percent": {"$gte": WORTH_BUYING_DISCOUNT}},
        ]

    # Đáy lịch sử lên trước, rồi tới mức giảm sâu nhất.
    cursor = (
        db.price_current.find(query, {"_id": 0})
        .sort([("is_historical_low", -1), ("discount_percent", -1)])
        .limit(limit)
    )

    rows = await cursor.to_list(None)
    deals = await _attach_games(db, rows)
    for deal in deals:
        deal["is_worth_buying"] = _is_worth_buying(deal)

    return {"deals": deals}


@router.get("/free-games")
async def get_free_games(request: Request, limit: int = Query(20, le=100)) -> dict[str, Any]:
    """Game free tuần này, gom mọi store."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    cursor = (
        db.price_current.find({"is_free_promo": True}, {"_id": 0})
        .sort("promo_ends_at", 1)
        .limit(limit)
    )

    free_games = await cursor.to_list(None)
    return {"free_games": await _attach_games(db, free_games)}
