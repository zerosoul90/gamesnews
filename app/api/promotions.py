from typing import Any

from fastapi import APIRouter

from app.core.deps import MongoDep
from app.services.promotions import get_active_banners, get_active_giftcodes

router = APIRouter(prefix="/promotions", tags=["promotions"])


@router.get("/banners")
async def fetch_banners(db: MongoDep) -> list[dict[str, Any]]:
    """Trả về lịch chạy banner hiện tại cho mobile app"""
    banners = await get_active_banners(db)
    return banners

@router.get("/games/{game_id}/giftcodes")
async def fetch_giftcodes(game_id: str, db: MongoDep) -> list[dict[str, Any]]:
    """Trả về list giftcode còn hạn của một game"""
    giftcodes = await get_active_giftcodes(db, game_id)
    return giftcodes
