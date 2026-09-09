"""WebSub cho YouTube — `docs/PHASE-7.md` mục 3.

Tài liệu chọn WebSub thay vì Data API vì một lý do rất cụ thể: quota Data API
là 10.000 unit/ngày và mỗi lần `search` tốn 100, tức khoảng 100 truy vấn/ngày.
WebSub thì YouTube tự đẩy về, **không tốn unit nào**.

Đổi lại, WebSub có hai chỗ dễ hỏng mà bản trước bỏ trống cả hai:

1. **Subscription hết hạn sau vài ngày.** `PHASE-7.md` viết thẳng: "Cần job
   gia hạn subscription định kỳ trước khi hết hạn — nếu quên thì thông báo im
   lặng chết mà không báo lỗi." Không có gì đỏ lên, chỉ là hết live nào được
   báo nữa.
2. **Ai cũng POST được vào endpoint công khai.** Không kiểm chữ ký thì bất kỳ
   ai cũng đẩy được "kênh X đang live" giả vào hệ thống. Cùng loại lỗ hổng với
   webhook Twitch.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

import feedparser
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

STREAMERS = "streamers"

# Hub cấp lease tối đa 10 ngày. Gia hạn sớm hơn hạn nhiều để một lượt job hỏng
# vẫn còn lượt sau cứu được, thay vì mất subscription.
RENEW_BEFORE = dt.timedelta(days=2)


@dataclass(frozen=True, slots=True)
class VideoEntry:
    """Một mục trong thân notification. Luôn có đúng một mục mỗi lần hub đẩy."""

    video_id: str
    channel_id: str
    title: str
    link: str | None
    published: str | None


def verify_signature(body: bytes, header: str | None, secret: str) -> bool:
    """Kiểm `X-Hub-Signature` của WebSub.

    Định dạng header là `sha1=<hex>`; hub cũng dùng sha256 nếu ta đăng ký như
    vậy, nên nhận cả hai. Thiếu secret thì trả False chứ **không** trả True:
    "chưa cấu hình" phải là từ chối, không phải cho qua.
    """
    if not secret or not header or "=" not in header:
        return False

    algorithm, _, signature = header.partition("=")
    digest = {"sha1": hashlib.sha1, "sha256": hashlib.sha256}.get(algorithm.lower())
    if digest is None:
        return False

    expected = hmac.new(secret.encode(), body, digest).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_notification(body: bytes) -> list[VideoEntry]:
    """Bóc thân Atom mà hub đẩy về.

    Dùng `feedparser` thay vì tự parse XML: nó đã lo phần namespace
    `yt:videoId` / `yt:channelId` (hiện ra thành `yt_videoid` / `yt_channelid`)
    và chịu được payload dị dạng mà không ném lỗi ra ngoài — endpoint webhook
    không được phép trả 500 chỉ vì một cú POST rác.
    """
    feed = feedparser.parse(body)
    entries: list[VideoEntry] = []

    for entry in feed.entries:
        video_id = entry.get("yt_videoid")
        channel_id = entry.get("yt_channelid")
        if not video_id or not channel_id:
            # Không đủ định danh thì không dùng vào việc gì được.
            continue
        entries.append(
            VideoEntry(
                video_id=str(video_id),
                channel_id=str(channel_id),
                title=str(entry.get("title") or ""),
                link=entry.get("link"),
                published=entry.get("published"),
            )
        )
    return entries


async def is_curated_channel(db: Db, channel_id: str) -> bool:
    """Kênh này có trong danh sách curate tay không?

    Tách khỏi `record_notification` vì thứ tự quan trọng: endpoint webhook là
    công khai, nên phải loại kênh lạ **trước** khi tiêu bất kỳ quota YouTube
    nào để hỏi xem video có đang live không. Không tách thì ai cũng đốt được
    quota của ta bằng cách POST payload giả.
    """
    return await db[STREAMERS].count_documents(
        {"platform": "youtube", "channel_id": channel_id}, limit=1
    ) > 0


async def record_notification(db: Db, entry: VideoEntry, *, is_live: bool = False) -> bool:
    """Ghi nhận một video/live mới. Trả về False nếu kênh không có trong danh sách.

    Chỉ nhận kênh đã curate (`PHASE-7.md` mục 6: danh sách streamer Việt do
    người chọn tay). Endpoint là công khai, nên kênh lạ đẩy vào thì bỏ qua —
    nếu không, ai cũng bơm dữ liệu vào bảng streamer được.

    `is_live` do người gọi quyết định, và mặc định là False. Thân notification
    của WebSub giống hệt nhau cho video mới đăng và buổi live vừa mở, nên bản
    trước cắm `is_live: True` cho **mọi** notification: một streamer đăng clip
    cắt là bảng "đang live" ghi tên họ, và chỉ có job dọn cờ sau 12 giờ mới gỡ
    ra được.
    """
    changes: dict[str, Any] = {
        "last_video_id": entry.video_id,
        "last_video_title": entry.title,
        "last_video_url": entry.link,
        "last_notified_at": dt.datetime.now(dt.UTC),
    }
    if is_live:
        changes["is_live"] = True

    result = await db[STREAMERS].update_one(
        {"platform": "youtube", "channel_id": entry.channel_id},
        {"$set": changes},
    )
    if result.matched_count == 0:
        logger.info(
            "bỏ qua notification của kênh không có trong danh sách",
            extra={"channel_id": entry.channel_id},
        )
        return False
    return True


async def mark_subscribed(db: Db, channel_id: str, lease_seconds: int) -> None:
    """Ghi hạn của subscription sau khi hub xác nhận.

    Không ghi thì job gia hạn không biết kênh nào sắp hết hạn, và toàn bộ cơ
    chế đẩy chết lặng lẽ sau vài ngày.
    """
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=max(lease_seconds, 0))
    await db[STREAMERS].update_one(
        {"platform": "youtube", "channel_id": channel_id},
        {"$set": {"websub_expires_at": expires}},
    )


async def due_for_renewal(db: Db, *, now: dt.datetime | None = None) -> list[str]:
    """Kênh cần gia hạn: sắp hết hạn, hoặc chưa từng đăng ký."""
    now = now or dt.datetime.now(dt.UTC)
    cursor = db[STREAMERS].find(
        {
            "platform": "youtube",
            "$or": [
                {"websub_expires_at": {"$lt": now + RENEW_BEFORE}},
                {"websub_expires_at": None},
            ],
        },
        {"channel_id": 1},
    )
    return [doc["channel_id"] async for doc in cursor if doc.get("channel_id")]
