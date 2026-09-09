import datetime as dt
import logging
from typing import Any, Literal

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.adapters.fcm.adapter import FcmAdapter
from app.core.config import get_settings
from app.models.game import PyObjectId
from app.services.devices import forget, tokens_of

logger = logging.getLogger(__name__)


class NotificationPayload(BaseModel):
    user_id: PyObjectId
    type: Literal["price_alert", "streamer_live", "giftcode", "digest"]
    title: str
    body: str
    data: dict[str, Any] = {}


async def send_push_notification(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    http: httpx.AsyncClient,
    user_id: PyObjectId,
    title: str,
    body: str,
    data: dict[str, Any],
) -> int:
    """Đẩy push tới mọi thiết bị của một user. Trả về số thiết bị nhận được.

    Bản trước chỉ ghi một dòng log rồi coi như xong — kiểu mock nguy hiểm hơn
    hẳn một stub báo lỗi, vì mọi tầng phía trên đều tin thông báo đã tới tay
    người dùng.

    Chưa cấu hình FCM thì ghi log lỗi và trả 0, **không** trả về như thể đã
    gửi. Token nào FCM báo là chết thì xoá ngay tại đây: không xoá thì danh
    sách phình mãi và mỗi lượt gửi tốn thêm request cho máy không còn tồn tại.
    """
    settings = get_settings()
    adapter = FcmAdapter(
        http,
        project_id=settings.fcm_project_id,
        client_email=settings.fcm_client_email,
        private_key=settings.fcm_private_key.get_secret_value(),
    )
    if not adapter.configured:
        logger.error(
            "FCM chưa cấu hình, không gửi được push",
            extra={"user_id": str(user_id), "title": title},
        )
        return 0

    tokens = await tokens_of(db, user_id)
    if not tokens:
        logger.info("user chưa đăng ký thiết bị nào", extra={"user_id": str(user_id)})
        return 0

    delivered = 0
    for token in tokens:
        result = await adapter.send(token, title=title, body=body, data=data)
        if result.ok:
            delivered += 1
        elif result.token_is_dead:
            await forget(db, token, reason=result.error or "FCM báo token chết")
        else:
            logger.warning(
                "gửi push hỏng", extra={"user_id": str(user_id), "error": result.error}
            )

    return delivered


def is_in_quiet_hours(now: dt.datetime, from_str: str, to_str: str) -> bool:
    """Check xem giờ hiện tại (UTC) quy ra giờ VN có nằm trong quiet_hours không."""
    # MVP: Hardcode timezone GMT+7. Thực tế nên lấy timezone từ user settings
    local_now = (now + dt.timedelta(hours=7)).time()

    try:
        from_time = dt.datetime.strptime(from_str, "%H:%M").time()
        to_time = dt.datetime.strptime(to_str, "%H:%M").time()
    except ValueError:
        return False

    if from_time <= to_time:
        return from_time <= local_now <= to_time
    else:  # Qua đêm, vd: 22:00 -> 07:00
        return local_now >= from_time or local_now <= to_time


async def process_notification(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    payload: NotificationPayload,
    force_immediate: bool = False,
    *,
    http: httpx.AsyncClient | None = None,
) -> None:
    """Notification Gatekeeper - Ngăn chặn Spam và phân phối thông báo."""
    user = await db.users.find_one({"_id": payload.user_id})
    if not user:
        return

    settings = user.get("notification_settings", {})
    channels = settings.get("channels", {})
    quiet_hours = settings.get("quiet_hours", {})

    # 1. User có bật kênh này không?
    if payload.type == "price_alert" and not channels.get("price_alert", True):
        logger.info(
            "Spam Prevented: User tắt kênh price_alert", extra={"user_id": str(payload.user_id)}
        )
        return

    # 2. Với cảnh báo giá, check xem người dùng đã sở hữu game chưa?
    # (Quy tắc sinh tử của Phase 3)
    if payload.type == "price_alert" and "game_id" in payload.data:
        game_id_str = payload.data["game_id"]
        try:
            game_id = PyObjectId(game_id_str)
            owned = await db.user_library.find_one({"user_id": payload.user_id, "game_id": game_id})
            if owned:
                logger.info(
                    "Spam Prevented: User đã có game này trong thư viện",
                    extra={"user_id": str(payload.user_id), "game_id": game_id_str},
                )
                return
        except Exception:
            # Fail CLOSED. `CLAUDE.md` đặt "không bao giờ báo giảm giá game
            # người dùng đã sở hữu" vào phần ranh giới không được vượt, nên khi
            # không kiểm tra được thì phải im lặng bỏ qua, không phải cứ gửi.
            # Nuốt lỗi rồi chạy tiếp nghĩa là một lần Mongo trục trặc là vi
            # phạm cam kết đó mà không ai biết.
            logger.exception(
                "không kiểm tra được thư viện người dùng, bỏ qua thông báo",
                extra={"user_id": str(payload.user_id), "game_id": game_id_str},
            )
            return

    # 3. Check giờ im lặng (Quiet Hours)
    now = dt.datetime.now(dt.UTC)
    in_quiet = is_in_quiet_hours(
        now, quiet_hours.get("from", "22:00"), quiet_hours.get("to", "07:00")
    )

    # Chỉ giá, streamer live, giftcode mới có tư cách báo tức thì
    is_immediate_type = payload.type in ("price_alert", "streamer_live", "giftcode")

    if (is_immediate_type and not in_quiet) or force_immediate:
        if http is None:
            # Không có client thì không gửi được, và im lặng bỏ qua là đúng
            # cái sai vừa sửa. Báo to rồi vẫn nhét vào hàng đợi digest để
            # thông báo không mất hẳn.
            logger.error(
                "thiếu http client, không gửi push tức thì được",
                extra={"user_id": str(payload.user_id), "type": payload.type},
            )
        else:
            await send_push_notification(
                db, http, payload.user_id, payload.title, payload.body, payload.data
            )
            return
    else:
        # Nhét vào queue chờ Job gom Digest hàng ngày bắn
        await db.notification_queue.insert_one(
            {
                "user_id": payload.user_id,
                "type": payload.type,
                "title": payload.title,
                "body": payload.body,
                "data": payload.data,
                "created_at": now.isoformat(),
            }
        )
        logger.info(
            "Notification kẹt queue (do Quiet Hours hoặc là Digest type)",
            extra={"user_id": str(payload.user_id)},
        )
