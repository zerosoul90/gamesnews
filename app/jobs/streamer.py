"""Job streamer — `docs/PHASE-7.md` mục 2, 3.

`job_renew_youtube_websub` là job dễ bị coi nhẹ nhất trong cả dự án, và tài
liệu nói thẳng vì sao:

> Cần job gia hạn subscription định kỳ trước khi hết hạn — **nếu quên thì
> thông báo im lặng chết mà không báo lỗi.**

Không có exception nào, không có log đỏ nào. Chỉ là sau vài ngày, không kênh
nào báo live nữa, và phải có người để ý mới phát hiện. Bản trước của job này
là một dòng `logger.info` rồi `pass`.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError
from app.adapters.youtube.adapter import YouTubeAdapter
from app.core.config import get_settings
from app.services.websub import due_for_renewal

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def job_sync_streamers(ctx: dict[str, Any]) -> dict[str, int]:
    """Quét lại trạng thái live, làm lưới đỡ cho cơ chế đẩy.

    Webhook có thể trượt: hub gặp lỗi, endpoint ta chết một lúc, subscription
    hết hạn giữa hai lượt gia hạn. Job này gỡ cờ `is_live` của kênh đã lâu
    không có tín hiệu, để bảng "đang live" không kẹt vĩnh viễn với một kênh đã
    tắt từ hôm qua.

    Chưa gọi API nào ở đây: Twitch cần key mà tài khoản không lấy được, còn
    YouTube `search` tốn 100 unit mỗi lần nên chỉ dành cho nhóm hot. Việc dọn
    cờ theo thời gian thì không cần gọi ra ngoài.
    """
    db: Db = ctx["clients"].db
    # Không có tín hiệu nào trong 12 giờ thì gần như chắc chắn đã tắt: một
    # phiên live dài hơn thế là rất hiếm, mà YouTube đẩy notification khi mở
    # live chứ không đẩy lúc kết thúc.
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(hours=12)
    result = await db.streamers.update_many(
        {"is_live": True, "last_notified_at": {"$lt": cutoff}},
        {"$set": {"is_live": False}},
    )
    logger.info("dọn cờ live quá hạn", extra={"cleared": result.modified_count})
    return {"cleared": result.modified_count}


async def job_renew_youtube_websub(ctx: dict[str, Any]) -> dict[str, int]:
    """Đăng ký lại WebSub cho kênh sắp hết hạn, hoặc chưa từng đăng ký."""
    db: Db = ctx["clients"].db
    settings = get_settings()

    if not settings.public_base_url:
        # Hub cần một URL công khai để đẩy về. Không có thì đăng ký chắc chắn
        # thất bại, nên báo to ở đây thay vì để nó hỏng lặng lẽ ở tầng dưới.
        logger.error("PUBLIC_BASE_URL chưa cấu hình, không đăng ký WebSub được")
        return {"renewed": 0, "failed": 0}

    channels = await due_for_renewal(db)
    if not channels:
        return {"renewed": 0, "failed": 0}

    adapter = YouTubeAdapter(ctx["clients"].http, settings.youtube_api_key.get_secret_value())
    callback = f"{settings.public_base_url.rstrip('/')}/webhooks/youtube"

    renewed = 0
    failed = 0
    for channel_id in channels:
        try:
            ok = await adapter.subscribe_websub(channel_id, callback)
        except AdapterError as exc:
            # Một kênh hỏng không được chặn những kênh còn lại.
            failed += 1
            logger.warning(
                "đăng ký WebSub hỏng", extra={"channel_id": channel_id, "error": repr(exc)}
            )
            continue
        renewed += int(bool(ok))
        failed += int(not ok)

    # `websub_expires_at` KHÔNG được cập nhật ở đây: hub xác nhận không đồng
    # bộ, và hạn thật chỉ biết được khi nó gọi ngược lại endpoint verify.
    logger.info("gia hạn WebSub", extra={"due": len(channels), "renewed": renewed})
    return {"renewed": renewed, "failed": failed}
