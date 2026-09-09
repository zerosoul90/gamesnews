import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.adapters.twitch.adapter import TwitchAdapter
from app.core.config import Settings, get_settings
from app.core.deps import MongoDep
from app.services.websub import (
    mark_subscribed,
    parse_notification,
    record_notification,
    verify_signature,
)

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
    db: MongoDep,
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_topic: str | None = Query(None, alias="hub.topic"),
    hub_lease_seconds: int | None = Query(None, alias="hub.lease_seconds"),
) -> Response:
    """Xác minh challenge của hub, và ghi lại hạn lease.

    Tên tham số của WebSub có dấu chấm (`hub.mode`), không phải gạch dưới, nên
    bắt buộc phải khai `alias`. Bản trước nhận `hub_mode` nên **không bao giờ
    khớp** tham số thật hub gửi, và mọi lần đăng ký đều trả 400 — subscription
    chưa từng thành lập được.

    Ghi hạn lease ngay ở đây: đó là chỗ duy nhất hub nói cho ta biết
    subscription sống được bao lâu.
    """
    if hub_mode not in ("subscribe", "unsubscribe") or not hub_challenge:
        raise HTTPException(status_code=400, detail="Invalid request")

    if hub_mode == "subscribe" and hub_topic and hub_lease_seconds:
        channel_id = parse_qs(urlparse(hub_topic).query).get("channel_id", [""])[0]
        if channel_id:
            await mark_subscribed(db, channel_id, hub_lease_seconds)

    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/youtube")
async def youtube_websub_notification(
    request: Request,
    db: MongoDep,
    settings: Settings = Depends(get_settings),
    signature: str | None = Header(None, alias="X-Hub-Signature"),
) -> Response:
    """Nhận notification video mới / mở live từ hub PubSubHubbub.

    Trả 204 kể cả khi không xử lý được gì: hub coi mọi mã 2xx là đã nhận, còn
    mã lỗi thì nó gửi lại nhiều lần rồi cuối cùng huỷ subscription. Một payload
    lạ không đáng để mất cả subscription.
    """
    body = await request.body()

    secret = settings.youtube_websub_secret.get_secret_value()
    if not secret:
        logger.error("YOUTUBE_WEBSUB_SECRET chưa cấu hình, từ chối webhook")
        raise HTTPException(status_code=503, detail="Webhook chưa được cấu hình")

    if not verify_signature(body, signature, secret):
        # 403 chứ không phải 204: đây là kẻ lạ, không phải hub.
        logger.warning("chữ ký WebSub không hợp lệ")
        raise HTTPException(status_code=403, detail="Invalid signature")

    recorded = 0
    for entry in parse_notification(body):
        if await record_notification(db, entry):
            recorded += 1

    logger.info("nhận WebSub YouTube", extra={"bytes": len(body), "recorded": recorded})
    return Response(status_code=204)
