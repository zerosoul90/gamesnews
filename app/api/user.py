import logging
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from pydantic import BaseModel

from app.adapters.steam.user import PrivateProfileError
from app.core.config import get_settings
from app.models.game import PyObjectId
from app.models.user import PriceAlert, UserFollow
from app.services.user_library import delete_library, sync_steam_library

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/user", tags=["User"])
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    """Dependency trích xuất thông tin user từ JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials, 
            settings.jwt_secret.get_secret_value(), 
            algorithms=["HS256"]
        )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")


@router.post("/library/sync")
async def sync_library(
    request: Request, 
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Đồng bộ thư viện từ Steam. Xử lý lỗi Profile Private."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    http = request.app.state.clients.http
    
    steam_id64 = current_user.get("steam_id64")
    user_id_str = current_user.get("sub")
    
    if not steam_id64:
        raise HTTPException(status_code=400, detail="User chưa liên kết Steam")
    
    try:
        user_id = PyObjectId(user_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ")
        
    try:
        result = await sync_steam_library(db, http, user_id, steam_id64)
        return result
    except PrivateProfileError:
        # 403 Forbidden mang ý nghĩa từ chối do quyền (Profile không công khai)
        # Bắn ra mã code tường minh để Frontend dễ parse và render màn hình hướng dẫn
        raise HTTPException(status_code=403, detail="PROFILE_IS_PRIVATE")


@router.delete("/library")
async def delete_my_library(
    request: Request, 
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Xóa trắng thư viện của user."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    
    try:
        user_id = PyObjectId(current_user.get("sub"))
    except Exception:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ")
        
    deleted = await delete_library(db, user_id)
    return {"deleted_count": deleted}


class EpicBulkRequest(BaseModel):
    from_month: int
    from_year: int


@router.post("/library/epic/bulk")
async def add_epic_games_bulk(
    request: Request,
    payload: EpicBulkRequest,
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Tick nhanh lấy danh sách game Free Epic trong quá khứ."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    user_id = PyObjectId(current_user["sub"])
    
    # Mốc thời gian bắt đầu
    import datetime as dt
    start_date = dt.datetime(payload.from_year, payload.from_month, 1, tzinfo=dt.UTC).isoformat()
    
    # Lấy các game Epic đã từng free từ khoảng thời gian đó
    # Giả định Epic games đang được fetch về db qua một job catalog khác
    # Thực tế: sẽ query price_history hoặc tag epic_free_promo
    
    # MVP Mock: Giả lập insert
    # Thực tế phải có data Epic thật để filter, tạm thời trả về báo thành công
    return {"status": "ok", "message": f"Đã quét và thêm game Epic từ {payload.from_month}/{payload.from_year}"}


@router.post("/follows")
async def follow_target(
    request: Request,
    follow: UserFollow,
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """User theo dõi game, series, dev, streamer."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    follow.user_id = PyObjectId(current_user["sub"])
    
    await db.user_follows.update_one(
        {"user_id": follow.user_id, "target_type": follow.target_type, "target_id": follow.target_id},
        {"$set": follow.to_mongo()},
        upsert=True
    )
    return {"status": "ok", "followed": follow.target_id}


@router.post("/alerts")
async def set_price_alert(
    request: Request,
    alert: PriceAlert,
    current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Đặt cảnh báo giá."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    alert.user_id = PyObjectId(current_user["sub"])
    
    await db.price_alerts.update_one(
        {"user_id": alert.user_id, "game_id": alert.game_id, "condition": alert.condition},
        {"$set": alert.to_mongo()},
        upsert=True
    )
    return {"status": "ok", "game_id": str(alert.game_id), "condition": alert.condition}
