import datetime as dt
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.adapters.base import AdapterError
from app.adapters.twitch.adapter import TwitchAdapter
from app.adapters.youtube.adapter import YouTubeAdapter
from app.core.config import Settings, get_settings
from app.core.deps import MongoDep
from app.services.streamers import notify_stream_live
from app.services.websub import (
    is_curated_channel,
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

    # Dùng client dùng chung của app, KHÔNG mở `httpx.AsyncClient()` mới ở
    # đây: mỗi request webhook sẽ mở một client rồi không bao giờ đóng, và
    # Twitch đẩy notification liên tục — connection và socket rò đều tay cho
    # tới khi tiến trình hết file descriptor.
    adapter = TwitchAdapter(
        request.app.state.clients.http,
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
        if type_ == "live" and broadcaster_id:
            await db.streamers.update_one(
                {"channel_id": broadcaster_id, "platform": "twitch"},
                {
                    "$set": {
                        "is_live": True,
                        "last_notified_at": dt.datetime.now(dt.UTC),
                    }
                },
            )
            # `stream_id` là định danh của buổi phát. EventSub gửi lại cùng một
            # notification khi ta trả lỗi hoặc trả chậm, nên phải chống trùng
            # theo buổi phát chứ không theo kênh.
            await notify_stream_live(
                db,
                platform="twitch",
                channel_id=str(broadcaster_id),
                stream_key=str(event.get("id") or broadcaster_id),
                title="Đang phát trực tiếp",
                url=f"https://twitch.tv/{event.get('broadcaster_user_login') or ''}",
                http=request.app.state.clients.http,
            )

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

    youtube = YouTubeAdapter(
        request.app.state.clients.http, settings.youtube_api_key.get_secret_value()
    )

    recorded = 0
    notified = 0
    for entry in parse_notification(body):
        # Loại kênh lạ TRƯỚC khi tiêu quota YouTube: endpoint này công khai.
        if not await is_curated_channel(db, entry.channel_id):
            continue

        # Notification của WebSub KHÔNG phân biệt video mới đăng với buổi live
        # vừa mở — cùng một thân Atom. Không hỏi lại thì mỗi clip cắt streamer
        # đăng lên sẽ đánh thức toàn bộ người theo dõi bằng một thông báo nói
        # rằng họ "đang live".
        try:
            live = await youtube.is_video_live(entry.video_id)
        except AdapterError as exc:
            # Ghi nhận video thì vẫn ghi — chỉ phần "có live không" là không
            # biết. Mất một lần push còn hơn mất cả dòng dữ liệu.
            logger.warning(
                "không kiểm được video có live không, bỏ qua push",
                extra={"video_id": entry.video_id, "error": repr(exc)},
            )
            live = None

        if live is None and not settings.youtube_api_key.get_secret_value():
            # Thiếu YOUTUBE_API_KEY thì không đời nào phân biệt được live với
            # video thường. Báo to, để lý do "sao không thấy push nào" hiện ra
            # trong log thay vì phải đoán.
            logger.warning("YOUTUBE_API_KEY chưa cấu hình: ghi nhận video nhưng không push")

        recorded += int(await record_notification(db, entry, is_live=bool(live)))

        if not live:
            continue

        # Chốt "push streamer live trong 60 giây" của `PHASE-7.md` nằm ở đúng
        # dòng này: hub đẩy về là gửi ngay, không đợi job nào cả.
        notified += await notify_stream_live(
            db,
            platform="youtube",
            channel_id=entry.channel_id,
            stream_key=entry.video_id,
            title=entry.title,
            url=entry.link,
            http=request.app.state.clients.http,
        )

    logger.info(
        "nhận WebSub YouTube",
        extra={"bytes": len(body), "recorded": recorded, "notified": notified},
    )
    return Response(status_code=204)
