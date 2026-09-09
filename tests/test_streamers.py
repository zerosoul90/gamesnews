"""Báo streamer lên sóng — `app/services/streamers.py` và webhook YouTube.

Đây là nửa còn thiếu của checkpoint Phase 7 ("push streamer live trong 60
giây"): đường tín hiệu từ hub về tới `is_live` đã có sẵn, nhưng chỗ đáng ra
gửi push chỉ có một dòng `# Todo`.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.youtube.adapter import YouTubeAdapter
from app.services.streamers import notify_stream_live
from app.services.websub import VideoEntry, is_curated_channel, record_notification

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def seed(db: Db, *, channel_id: str = "UC_viet") -> tuple[ObjectId, ObjectId]:
    """Một streamer đã curate + một user đang theo dõi họ. Trả về (streamer, user)."""
    streamer_id = ObjectId()
    user_id = ObjectId()

    await db.streamers.insert_one(
        {
            "_id": streamer_id,
            "platform": "youtube",
            "channel_id": channel_id,
            "display_name": "Độ Mixi",
        }
    )
    await db.users.insert_one({"_id": user_id, "notification_settings": {}})
    await db.user_follows.insert_one(
        {"user_id": user_id, "target_type": "streamer", "target_id": streamer_id}
    )
    return streamer_id, user_id


async def test_bao_cho_nguoi_theo_doi(mongo_db: Db) -> None:
    _, user_id = await seed(mongo_db)

    sent = await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_viet", stream_key="video1"
    )

    assert sent == 1
    # Không có http client nên thông báo hạ xuống hàng đợi digest thay vì mất.
    queued = await mongo_db.notification_queue.find_one({"user_id": user_id})
    assert queued is not None
    assert queued["type"] == "streamer_live"
    assert "Độ Mixi" in queued["title"]


async def test_cung_mot_buoi_phat_khong_bao_hai_lan(mongo_db: Db) -> None:
    """Hub WebSub cố ý đẩy lại nhiều lần; người xem không được nhận hai lần."""
    await seed(mongo_db)

    first = await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_viet", stream_key="video1"
    )
    second = await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_viet", stream_key="video1"
    )

    assert (first, second) == (1, 0)
    assert await mongo_db.notification_queue.count_documents({}) == 1


async def test_buoi_phat_moi_thi_bao_lai(mongo_db: Db) -> None:
    await seed(mongo_db)

    await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_viet", stream_key="video1"
    )
    again = await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_viet", stream_key="video2"
    )

    assert again == 1
    assert await mongo_db.notification_queue.count_documents({}) == 2


async def test_kenh_khong_trong_danh_sach_thi_khong_gui_gi(mongo_db: Db) -> None:
    """Endpoint webhook là công khai: kênh lạ không được làm ta gửi bất cứ gì."""
    await seed(mongo_db)

    sent = await notify_stream_live(
        mongo_db, platform="youtube", channel_id="UC_nguoi_la", stream_key="v"
    )

    assert sent == 0
    assert await mongo_db.notification_queue.count_documents({}) == 0


async def test_kiem_kenh_da_curate(mongo_db: Db) -> None:
    await seed(mongo_db)
    assert await is_curated_channel(mongo_db, "UC_viet") is True
    assert await is_curated_channel(mongo_db, "UC_la") is False


async def test_video_thuong_khong_cam_co_is_live(mongo_db: Db) -> None:
    """Thân notification của WebSub giống hệt nhau cho video mới và buổi live.

    Bản trước cắm `is_live: True` cho mọi notification, nên một clip cắt đăng
    lên là bảng "đang live" ghi tên streamer suốt 12 tiếng, tới khi job dọn cờ
    chạy.
    """
    await seed(mongo_db)
    entry = VideoEntry(
        video_id="v1", channel_id="UC_viet", title="Highlight hôm qua", link=None, published=None
    )

    assert await record_notification(mongo_db, entry, is_live=False) is True

    doc = await mongo_db.streamers.find_one({"channel_id": "UC_viet"})
    assert doc is not None
    assert doc.get("is_live") is not True
    assert doc["last_video_id"] == "v1"


async def test_live_that_thi_cam_co(mongo_db: Db) -> None:
    await seed(mongo_db)
    entry = VideoEntry(
        video_id="v2", channel_id="UC_viet", title="Live PUBG", link=None, published=None
    )

    await record_notification(mongo_db, entry, is_live=True)

    doc = await mongo_db.streamers.find_one({"channel_id": "UC_viet"})
    assert doc is not None
    assert doc["is_live"] is True


# --- Adapter: phân biệt live với video thường ------------------------------


def youtube_with(payload: dict[str, Any], *, key: str = "k") -> YouTubeAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return YouTubeAdapter(httpx.AsyncClient(transport=httpx.MockTransport(handler)), key)


@pytest.mark.parametrize(
    ("content", "expected"),
    [("live", True), ("none", False), ("upcoming", False)],
)
async def test_doc_dung_trang_thai_live(content: str, expected: bool) -> None:
    adapter = youtube_with({"items": [{"snippet": {"liveBroadcastContent": content}}]})
    assert await adapter.is_video_live("v") is expected


async def test_khong_co_key_thi_tra_none_khong_phai_false() -> None:
    """None = "không biết", False = "biết chắc là không live". Khác nhau."""
    adapter = youtube_with({}, key="")
    assert await adapter.is_video_live("v") is None


async def test_video_bi_go_thi_tra_none() -> None:
    adapter = youtube_with({"items": []})
    assert await adapter.is_video_live("v") is None
