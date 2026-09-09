import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.adapters.steam.user import PrivateProfileError
from app.api.auth import get_current_user
from app.models.game import PyObjectId
from app.models.user import PriceAlert, UserFollow
from app.services import devices
from app.services.user_library import delete_library, sync_steam_library

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/user", tags=["User"])


def db_of(request: Request) -> AsyncIOMotorDatabase[dict[str, Any]]:
    database: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    return database


@router.post("/library/sync")
async def sync_library(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
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
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ") from exc

    try:
        result = await sync_steam_library(db, http, user_id, steam_id64)
        return result
    except PrivateProfileError as exc:
        # 403 mang nghĩa từ chối vì quyền (profile không công khai). Mã lỗi
        # tường minh để frontend render đúng màn hình hướng dẫn mở profile.
        raise HTTPException(status_code=403, detail="PROFILE_IS_PRIVATE") from exc


@router.delete("/library")
async def delete_my_library(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Xóa trắng thư viện của user."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    try:
        user_id = PyObjectId(current_user.get("sub"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ") from exc

    deleted = await delete_library(db, user_id)
    return {"deleted_count": deleted}


class EpicBulkRequest(BaseModel):
    from_month: int
    from_year: int


@router.post("/library/epic/bulk")
async def add_epic_games_bulk(
    request: Request,
    payload: EpicBulkRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Tick nhanh lấy danh sách game Free Epic trong quá khứ.

    CHƯA LÀM. Trước đây hàm này trả về {"status": "ok", "message": "Đã quét và
    thêm..."} trong khi không đụng vào database — client tin là xong, người
    dùng tưởng thư viện đã có game. Trả 501 cho tới khi có dữ liệu Epic thật:
    im lặng thất bại còn tệ hơn thất bại ồn ào.

    Cần trước khi làm được: job catalog Epic đánh dấu game từng free theo tuần
    (`price_history` hoặc cờ `epic_free_promo`).
    """
    raise HTTPException(
        status_code=501,
        detail="Chưa hỗ trợ: cần dữ liệu game free Epic theo tuần trước đã.",
    )


class DeviceRegistration(BaseModel):
    """Token FCM của một thiết bị."""

    fcm_token: str = Field(min_length=1, max_length=4096)
    # Tên trường khớp đúng cái app Flutter đang gửi (`device_type`).
    device_type: Literal["android", "ios", "web"] = "android"


@router.post("/device")
async def register_device(
    request: Request,
    payload: DeviceRegistration,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Ghi nhận thiết bị để gửi push.

    Endpoint này **chưa từng tồn tại**, trong khi `mobile/lib/core/
    notification_service.dart` đã POST tới đúng đường dẫn này và bắt lỗi bằng
    một dòng `debugPrint`. Tức là mọi lần cài app đều nhận 404, log một dòng
    rồi đi tiếp — không ai thấy, và không thiết bị nào bao giờ nhận được push.
    """
    try:
        user_id = PyObjectId(current_user.get("sub"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ") from exc

    is_new = await devices.register(
        db_of(request), user_id, payload.fcm_token, platform=payload.device_type
    )
    return {"status": "ok", "is_new_device": is_new}


@router.delete("/device")
async def unregister_device(
    request: Request,
    payload: DeviceRegistration,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Gỡ một thiết bị — dùng khi người dùng đăng xuất trên máy đó."""
    removed = await devices.forget(db_of(request), payload.fcm_token, reason="user đăng xuất")
    return {"status": "ok", "removed": removed}


@router.post("/follows")
async def follow_target(
    request: Request, follow: UserFollow, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """User theo dõi game, series, dev, streamer."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    follow.user_id = PyObjectId(current_user["sub"])

    await db.user_follows.update_one(
        {
            "user_id": follow.user_id,
            "target_type": follow.target_type,
            "target_id": follow.target_id,
        },
        {"$set": follow.to_mongo()},
        upsert=True,
    )
    return {"status": "ok", "followed": follow.target_id}


@router.post("/alerts")
async def set_price_alert(
    request: Request, alert: PriceAlert, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Đặt cảnh báo giá."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    alert.user_id = PyObjectId(current_user["sub"])

    await db.price_alerts.update_one(
        {"user_id": alert.user_id, "game_id": alert.game_id, "condition": alert.condition},
        {"$set": alert.to_mongo()},
        upsert=True,
    )
    return {"status": "ok", "game_id": str(alert.game_id), "condition": alert.condition}


@router.get("/me/wrapped/{year}")
async def get_user_wrapped(
    year: int, request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Lấy dữ liệu tổng kết năm (Year in Review) của user"""
    from app.services.wrapped import generate_year_in_review

    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ")

    wrapped_data = await generate_year_in_review(db, user_id, year)
    if not wrapped_data:
        raise HTTPException(status_code=404, detail="Chưa đủ dữ liệu để tổng kết")
    return wrapped_data
