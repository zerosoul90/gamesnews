import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.adapters.twitch.adapter import TwitchAdapter
from app.core.config import Settings, get_settings
from app.core.deps import MongoDep

logger = logging.getLogger(__name__)

router = APIRouter()


# `response_model=None`: hàm trả về Response (cho bước challenge của Twitch)
# HOẶC dict (cho notification). FastAPI không dựng được response model từ
# union đó, và ở đây ta cũng không cần nó dựng.
@router.post("/twitch", response_model=None)
async def twitch_eventsub(
    request: Request,
    db: MongoDep,
    settings: Settings = Depends(get_settings),
    message_id: str = Header(..., alias="Twitch-Eventsub-Message-Id"),
    message_timestamp: str = Header(..., alias="Twitch-Eventsub-Message-Timestamp"),
    message_signature: str = Header(..., alias="Twitch-Eventsub-Message-Signature"),
    message_type: str = Header(..., alias="Twitch-Eventsub-Message-Type"),
) -> Response | dict[str, Any]:
    """
    Webhook nhận notification từ Twitch EventSub.
    """
    body = await request.body()

    # Trước đây chỗ này dựng adapter mà KHÔNG truyền webhook_secret, nên nó rơi
    # về giá trị mặc định "your_webhook_secret_here" viết cứng trong adapter.
    # Chuỗi đó nằm trong mã nguồn công khai, nghĩa là bất kỳ ai cũng ký được một
    # notification hợp lệ và đẩy trạng thái streamer giả vào hệ thống.
    webhook_secret = settings.twitch_webhook_secret.get_secret_value()
    if not webhook_secret:
        # Không cấu hình thì đóng hẳn. Kiểm chữ ký với secret rỗng chỉ tạo cảm
        # giác an toàn chứ không chặn được ai.
        logger.error("TWITCH_WEBHOOK_SECRET chưa cấu hình, từ chối webhook")
        raise HTTPException(status_code=503, detail="Webhook chưa được cấu hình")

    adapter = TwitchAdapter(
        httpx.AsyncClient(),
        client_id=settings.twitch_client_id,
        client_secret=settings.twitch_client_secret.get_secret_value(),
        webhook_secret=webhook_secret,
    )

    # 1. Verify Signature
    if not adapter.verify_eventsub_signature(
        message_id, message_timestamp, body, message_signature
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Xử lý Challenge (khi setup webhook)
    payload = await request.json()
    if message_type == "webhook_callback_verification":
        return Response(content=payload.get("challenge"), media_type="text/plain")

    # 3. Xử lý Notification
    if message_type == "notification":
        event = payload.get("event", {})
        # Lấy thông tin streamer live
        broadcaster_id = event.get("broadcaster_user_id")
        type_ = event.get("type")  # "live"

        # Cập nhật DB
        if type_ == "live":
            await db.streamers.update_one(
                {"channel_id": broadcaster_id, "platform": "twitch"}, {"$set": {"is_live": True}}
            )
            # Todo: Push Notification tới FCM cho User
            logger.info(f"Streamer {broadcaster_id} is live!")

    return {"status": "ok"}


@router.get("/youtube")
async def youtube_websub_verify(
    request: Request,
    hub_mode: str | None = None,
    hub_challenge: str | None = None,
    hub_topic: str | None = None,
) -> Response:
    """
    Webhook xác minh Challenge từ YouTube PubSubHubbub.
    """
    if hub_mode in ("subscribe", "unsubscribe") and hub_challenge:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/youtube")
async def youtube_websub_notification(
    request: Request,
    db: MongoDep,
) -> Response:
    """
    Webhook nhận notification từ YouTube PubSubHubbub (XML Feed).
    """
    # Vẫn phải đọc hết body trước khi trả lời, nếu không phía gửi có thể coi
    # là kết nối bị cắt giữa chừng và gửi lại.
    body = await request.body()
    # CHƯA LÀM: parse XML feed để lấy video mới / livestream.
    logger.info("nhận WebSub YouTube nhưng chưa xử lý", extra={"bytes": len(body)})
    return Response(status_code=204)
