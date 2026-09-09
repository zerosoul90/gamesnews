from typing import Any

from fastapi import APIRouter, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats")
async def get_dashboard_stats(request: Request) -> dict[str, Any]:
    """
    Thống kê chung (Dashboard 1):
    Tổng số game, số deal hiện tại, số free game, số game đạt đáy lịch sử.
    """
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    total_games = await db.games.count_documents({})
    total_deals = await db.price_current.count_documents({"discount_percent": {"$gt": 0}})
    total_free = await db.price_current.count_documents({"is_free_promo": True})
    total_historical_lows = await db.price_current.count_documents({"is_historical_low": True})

    return {
        "total_games_tracked": total_games,
        "total_deals_now": total_deals,
        "total_free_games": total_free,
        "total_historical_lows": total_historical_lows
    }
