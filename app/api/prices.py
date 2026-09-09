import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.game import PyObjectId
from app.models.price import PriceCurrent, PriceHistory

router = APIRouter(tags=["Prices & Deals"])

@router.get("/games/{game_id}/prices")
async def get_prices(request: Request, game_id: PyObjectId) -> dict[str, Any]:
    """Giá hiện tại mọi store, mọi region đang theo dõi."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    game = await db.games.find_one({"_id": game_id})
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
        
    cursor = db.price_current.find({"game_id": game_id}, {"_id": 0})
    prices = await cursor.to_list(None)
    return {"prices": prices}


@router.get("/games/{game_id}/price-history")
async def get_price_history(request: Request, game_id: PyObjectId, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    """Dữ liệu vẽ biểu đồ lịch sử giá."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).isoformat()
    
    cursor = db.price_history.find(
        {"game_id": game_id, "changed_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("changed_at", 1)
    
    history = await cursor.to_list(None)
    return {"history": history}


@router.get("/deals")
async def get_deals(request: Request, limit: int = Query(20, le=100)) -> dict[str, Any]:
    """Danh sách deal sắp xếp theo chất lượng deal."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    
    # Sort deals by historical low first, then by discount percent
    cursor = db.price_current.find(
        {"discount_percent": {"$gt": 0}},
        {"_id": 0}
    ).sort([("is_historical_low", -1), ("discount_percent", -1)]).limit(limit)
    
    deals = await cursor.to_list(None)
    return {"deals": deals}


@router.get("/free-games")
async def get_free_games(request: Request, limit: int = Query(20, le=100)) -> dict[str, Any]:
    """Game free tuần này, gom mọi store."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    
    cursor = db.price_current.find(
        {"is_free_promo": True},
        {"_id": 0}
    ).sort("promo_ends_at", 1).limit(limit)
    
    free_games = await cursor.to_list(None)
    return {"free_games": free_games}
