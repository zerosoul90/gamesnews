"""Báo streamer lên sóng — `docs/PHASE-7.md`.

Checkpoint của Phase 7 có hai vế, và trước đây chỉ vế đầu được làm:

> bảng "Đang tăng mạnh" không bị game top thường trực chiếm chỗ; **push
> streamer live trong 60 giây.**

Đường đi tín hiệu đã hoàn chỉnh từ trước: hub WebSub đẩy về `/webhooks/youtube`
→ `websub.record_notification` cắm cờ `is_live`. Chỗ đứt là ngay sau đó — cả
webhook YouTube lẫn webhook Twitch chỉ ghi cờ rồi dừng, chỗ đáng ra phải gửi
push để lại đúng một dòng `# Todo`. Nghĩa là cột "60 giây" chưa từng được tính
từ đâu tới đâu: không có thông báo nào rời khỏi hệ thống.

Hai chốt của file này:

1. **Chống báo lại.** Hub đẩy notification nhiều lần cho cùng một video (đó là
   thiết kế của WebSub — thà gửi thừa còn hơn mất), và job quét lưới đỡ có thể
   bật lại cờ. Người theo dõi không được nhận cùng một buổi live hai lần, nên
   mốc chống trùng là **video/stream id**, không phải cờ `is_live`.
2. **Đi qua đúng Gatekeeper.** Không gọi thẳng `send_push_notification`: giờ im
   lặng, kênh bị tắt và hàng đợi digest đều nằm trong `process_notification`,
   và một loại thông báo mới không được phép là ngoại lệ của những luật đó.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.notification import NotificationPayload, process_notification

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

STREAMERS = "streamers"


async def notify_stream_live(
    db: Db,
    *,
    platform: str,
    channel_id: str,
    stream_key: str,
    title: str = "",
    url: str | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Báo cho người theo dõi rằng một kênh vừa lên sóng.

    `stream_key` là định danh của **buổi phát** (video id của YouTube, stream
    id của Twitch), không phải của kênh. Trả về số người đã được xử lý; 0 nếu
    kênh lạ hoặc buổi phát này đã báo rồi.
    """
    streamer = await db[STREAMERS].find_one({"platform": platform, "channel_id": channel_id})
    if streamer is None:
        # Endpoint webhook là công khai. Kênh không có trong danh sách curate
        # thì không được phép làm hệ thống gửi đi bất cứ thứ gì.
        return 0

    if streamer.get("last_notified_stream") == stream_key:
        logger.info(
            "buổi phát này đã báo rồi, bỏ qua",
            extra={"channel_id": channel_id, "stream_key": stream_key},
        )
        return 0

    # Chiếm chỗ TRƯỚC khi gửi. Hub hay đẩy lại rất nhanh; đánh dấu sau khi gửi
    # xong thì hai notification chồng nhau đều thấy mốc cũ và cùng gửi.
    claimed = await db[STREAMERS].update_one(
        {
            "platform": platform,
            "channel_id": channel_id,
            "last_notified_stream": {"$ne": stream_key},
        },
        {"$set": {"last_notified_stream": stream_key}},
    )
    if claimed.modified_count == 0:
        return 0

    display_name = streamer.get("display_name") or channel_id
    payload_title = f"{display_name} đang live"
    body = title or "Bấm để xem ngay"

    sent = 0
    async for follow in db.user_follows.find(
        {"target_type": "streamer", "target_id": streamer["_id"]}
    ):
        user_id = follow.get("user_id")
        if not isinstance(user_id, ObjectId):
            continue
        await process_notification(
            db,
            NotificationPayload(
                user_id=user_id,
                type="streamer_live",
                title=payload_title,
                body=body,
                data={
                    "streamer_id": str(streamer["_id"]),
                    "platform": platform,
                    "channel_id": channel_id,
                    "url": url or "",
                },
            ),
            http=http,
        )
        sent += 1

    logger.info(
        "báo streamer live",
        extra={"channel_id": channel_id, "platform": platform, "followers": sent},
    )
    return sent
