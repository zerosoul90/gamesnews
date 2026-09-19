import logging
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.adapters.steam.user import PrivateProfileError
from app.api.auth import get_current_user
from app.models.game import PyObjectId
from app.models.user import ConditionType, PriceAlert, TargetType, UserFollow
from app.services import devices, user_reads
from app.services.user_library import delete_library, sync_steam_library

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/user", tags=["User"])


def db_of(request: Request) -> AsyncIOMotorDatabase[dict[str, Any]]:
    database: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    return database


def _user_id(current_user: dict[str, Any]) -> ObjectId:
    """`_id` của người đang đăng nhập, từ claim `sub`.

    Gom về một chỗ vì trước đó bốn endpoint chép lại cùng một khối try/except —
    và bản chép nào cũng có cơ hội quên, mà quên ở đây nghĩa là `PyObjectId(None)`
    ném lỗi thành 500 thay vì 400.
    """
    try:
        return PyObjectId(current_user.get("sub"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID user không hợp lệ") from exc


def _object_id(value: str, ten: str) -> ObjectId:
    """Đổi tham số đường dẫn sang `ObjectId`, 400 nếu sai dạng.

    Không để `ObjectId(value)` ném thẳng: `bson.errors.InvalidId` không phải
    `HTTPException` nên FastAPI trả 500 cho một lỗi rõ ràng là của client.
    """
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail=f"{ten} không hợp lệ")
    return ObjectId(value)


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


# --- thân request cho hai đường GHI ------------------------------------------
#
# Tách khỏi `UserFollow` / `PriceAlert` vì hai model kia khai `user_id` là
# **bắt buộc**, mà giá trị client gửi lên lại bị ghi đè ngay bằng claim `sub`
# của JWT. Dùng thẳng chúng làm schema body gây ra hai chuyện, cái sau tệ hơn:
#
# 1. Client không gửi `user_id` thì ăn 422 — cho một trường mà server không hề
#    dùng. Web không gọi nổi endpoint nếu không bịa ra một giá trị.
# 2. Trường ấy nằm trong tài liệu OpenAPI như thể đặt được, nên người đọc hợp
#    lý sẽ tin là mình chỉ định được chủ sở hữu. Nó bị bỏ qua — nhưng nếu một
#    bản sửa sau này lỡ bỏ dòng ghi đè đi, nó thành lỗ leo thang quyền ngay.
#
# Bỏ hẳn khỏi schema thì cả hai chuyện không còn chỗ xảy ra.


# Dùng lại đúng `TargetType` / `ConditionType` của model thay vì khai `str`:
# giá trị lạ bị FastAPI chặn ở biên và trả **422**. Khai `str` thì nó lọt qua
# tầng này rồi mới chết trong constructor Pydantic — thành 500 cho một lỗi rõ
# ràng là của client, và thêm một chỗ nữa phải nhớ đồng bộ khi thêm loại mới.


class FollowRequest(BaseModel):
    target_type: TargetType
    target_id: str


class AlertRequest(BaseModel):
    game_id: str
    condition: ConditionType
    value: int | None = None
    currency: str = "VND"


@router.post("/follows")
async def follow_target(
    request: Request,
    payload: FollowRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """User theo dõi game, series, dev, streamer."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    # `target_id` của game lưu dạng ObjectId để join được với `games`; của
    # series/streamer là slug hoặc tên, giữ nguyên chuỗi. Xem `follows_of`.
    target_id: ObjectId | str = payload.target_id
    if payload.target_type == "game":
        target_id = _object_id(payload.target_id, "target_id")

    follow = UserFollow(
        user_id=_user_id(current_user),
        target_type=payload.target_type,
        target_id=target_id,
    )

    await db.user_follows.update_one(
        {
            "user_id": follow.user_id,
            "target_type": follow.target_type,
            "target_id": follow.target_id,
        },
        {"$set": follow.to_mongo()},
        upsert=True,
    )
    return {"status": "ok", "followed": str(follow.target_id)}


@router.post("/alerts")
async def set_price_alert(
    request: Request,
    payload: AlertRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Đặt cảnh báo giá."""
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db

    alert = PriceAlert(
        user_id=_user_id(current_user),
        game_id=_object_id(payload.game_id, "game_id"),
        condition=payload.condition,
        value=payload.value,
        currency=payload.currency,
    )

    await db.price_alerts.update_one(
        {"user_id": alert.user_id, "game_id": alert.game_id, "condition": alert.condition},
        {"$set": alert.to_mongo()},
        upsert=True,
    )
    return {"status": "ok", "game_id": str(alert.game_id), "condition": alert.condition}


@router.get("/library")
async def get_my_library(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Thư viện của tôi, chơi nhiều nhất trước.

    Trước endpoint này `/library` chỉ có `DELETE` và `POST /sync` — đồng bộ xong
    thì không có đường nào đọc lại, nên màn "Thư viện của tôi" không dựng được.
    """
    items, total = await user_reads.library_of(
        db_of(request), _user_id(current_user), limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/alerts")
async def get_my_alerts(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Cảnh báo giá của tôi.

    Mỗi mục có cờ `owned`: game đã nằm trong thư viện thì cảnh báo ấy sẽ **không
    bao giờ được gửi** (`services/notification.py` chặn, và chặn kiểu fail
    closed). Trả về kèm cờ thay vì giấu đi, để giao diện làm mờ và nói rõ lý do
    — cảnh báo do chính người dùng đặt mà biến mất không lời nào thì họ chỉ đặt
    lại.
    """
    alerts = await user_reads.alerts_of(db_of(request), _user_id(current_user))
    return {"alerts": alerts, "total": len(alerts)}


@router.delete("/alerts/{alert_id}")
async def delete_my_alert(
    alert_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Xoá một cảnh báo của CHÍNH MÌNH.

    404 chứ không phải 403 khi cảnh báo thuộc người khác: hai mã đó phân biệt
    được "không tồn tại" với "tồn tại nhưng không phải của bạn", và phân biệt ấy
    tự nó là rò rỉ thông tin.
    """
    ok = await user_reads.delete_alert(
        db_of(request), _user_id(current_user), _object_id(alert_id, "alert_id")
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    return {"status": "ok"}


@router.get("/follows")
async def get_my_follows(
    request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Những gì tôi đang theo dõi. `target` là `None` với mục không phải game."""
    follows = await user_reads.follows_of(db_of(request), _user_id(current_user))
    return {"follows": follows, "total": len(follows)}


@router.delete("/follows/{follow_id}")
async def delete_my_follow(
    follow_id: str, request: Request, current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """Bỏ theo dõi. Cùng luật 404 như `delete_my_alert`."""
    ok = await user_reads.delete_follow(
        db_of(request), _user_id(current_user), _object_id(follow_id, "follow_id")
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy mục theo dõi")
    return {"status": "ok"}


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
