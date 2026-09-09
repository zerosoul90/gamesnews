"""WebSub YouTube — `docs/PHASE-7.md` mục 3.

Hai thứ được kiểm kỹ nhất, vì hỏng cái nào cũng **không có lỗi nào nổi lên**:

- chữ ký giả phải bị chặn (endpoint là công khai, ai cũng POST được);
- subscription sắp hết hạn phải được nhặt ra để gia hạn — tài liệu ghi rõ
  "nếu quên thì thông báo im lặng chết mà không báo lỗi".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import pathlib
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.websub import (
    STREAMERS,
    due_for_renewal,
    mark_subscribed,
    parse_notification,
    record_notification,
    verify_signature,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
BODY = (FIXTURES / "youtube_websub.xml").read_bytes()

CHANNEL = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
SECRET = "bi-mat-cua-test"  # noqa: S105 - của test, không mở được gì


def sign(body: bytes, secret: str = SECRET, algorithm: str = "sha1") -> str:
    digest = {"sha1": hashlib.sha1, "sha256": hashlib.sha256}[algorithm]
    return f"{algorithm}={hmac.new(secret.encode(), body, digest).hexdigest()}"


# --- chữ ký ----------------------------------------------------------------


def test_chu_ky_dung_thi_qua() -> None:
    assert verify_signature(BODY, sign(BODY), SECRET) is True
    assert verify_signature(BODY, sign(BODY, algorithm="sha256"), SECRET) is True


def test_chu_ky_sai_thi_chan() -> None:
    khac = "bi-mat-khac"
    assert verify_signature(BODY, sign(BODY, secret=khac), SECRET) is False


def test_doi_mot_byte_trong_than_la_chu_ky_hong() -> None:
    assert verify_signature(BODY + b" ", sign(BODY), SECRET) is False


def test_thieu_secret_thi_tu_choi_chu_khong_cho_qua() -> None:
    """"Chưa cấu hình" phải là từ chối. Cho qua thì endpoint mở toang mà không
    ai biết, vì mọi thứ vẫn "chạy"."""
    assert verify_signature(BODY, sign(BODY), "") is False


def test_khong_co_header_hoac_dinh_dang_la_thi_chan() -> None:
    assert verify_signature(BODY, None, SECRET) is False
    assert verify_signature(BODY, "khong-co-dau-bang", SECRET) is False
    assert verify_signature(BODY, "md5=abc", SECRET) is False


# --- bóc payload -----------------------------------------------------------


def test_boc_dung_video_va_kenh_tu_than_atom() -> None:
    entries = parse_notification(BODY)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.video_id == "dQw4w9WgXcQ"
    assert entry.channel_id == CHANNEL
    assert entry.title == "Elden Ring Nightreign - Livestream ra mắt"
    assert entry.link == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_payload_rac_khong_lam_no_endpoint() -> None:
    """Endpoint webhook không được trả 500 vì một cú POST rác: hub sẽ gửi lại
    nhiều lần rồi huỷ subscription."""
    assert parse_notification(b"khong phai xml") == []
    assert parse_notification(b"<feed></feed>") == []


def test_thieu_dinh_danh_thi_bo_qua_muc_do() -> None:
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Khong co videoId</title></entry></feed>"""

    assert parse_notification(xml) == []


# --- ghi nhận và gia hạn ---------------------------------------------------


async def test_chi_nhan_kenh_da_co_trong_danh_sach(mongo_db: Db) -> None:
    """Endpoint công khai, nên kênh lạ đẩy vào phải bị bỏ qua — nếu không ai
    cũng bơm dữ liệu vào bảng streamer được."""
    entry = parse_notification(BODY)[0]

    assert await record_notification(mongo_db, entry) is False

    await mongo_db[STREAMERS].insert_one(
        {"platform": "youtube", "channel_id": CHANNEL, "display_name": "Kênh Game Việt"}
    )
    assert await record_notification(mongo_db, entry) is True

    doc = await mongo_db[STREAMERS].find_one({"channel_id": CHANNEL})
    assert doc is not None
    assert doc["last_video_id"] == "dQw4w9WgXcQ"
    # `is_live` KHÔNG được cắm ở đây nữa. Thân notification của WebSub giống
    # hệt nhau cho một video mới đăng và một buổi live vừa mở, nên bản trước
    # cắm cờ cho mọi notification: streamer đăng một clip cắt là bảng "đang
    # live" ghi tên họ tới khi job dọn cờ chạy, 12 giờ sau. Người gọi phải tự
    # xác định trạng thái (`YouTubeAdapter.is_video_live`) rồi truyền vào —
    # xem `tests/test_streamers.py`.
    assert "is_live" not in doc


async def test_kenh_chua_dang_ky_lan_nao_thi_can_gia_han(mongo_db: Db) -> None:
    await mongo_db[STREAMERS].insert_one(
        {"platform": "youtube", "channel_id": CHANNEL, "websub_expires_at": None}
    )

    assert await due_for_renewal(mongo_db) == [CHANNEL]


async def test_sap_het_han_thi_can_gia_han_som(mongo_db: Db) -> None:
    """Gia hạn sớm hơn hạn hai ngày: một lượt job hỏng vẫn còn lượt sau cứu
    được, thay vì mất subscription."""
    now = dt.datetime.now(dt.UTC)
    await mongo_db[STREAMERS].insert_many(
        [
            {
                "platform": "youtube",
                "channel_id": "sap-het",
                "websub_expires_at": now + dt.timedelta(hours=12),
            },
            {
                "platform": "youtube",
                "channel_id": "con-lau",
                "websub_expires_at": now + dt.timedelta(days=9),
            },
        ]
    )

    assert await due_for_renewal(mongo_db, now=now) == ["sap-het"]


async def test_ghi_han_lease_sau_khi_hub_xac_nhan(mongo_db: Db) -> None:
    """Không ghi thì job gia hạn không biết kênh nào sắp hết hạn, và cả cơ chế
    đẩy chết lặng lẽ sau vài ngày."""
    now = dt.datetime.now(dt.UTC)
    await mongo_db[STREAMERS].insert_one(
        {"platform": "youtube", "channel_id": CHANNEL, "websub_expires_at": None}
    )

    ten_days = int(dt.timedelta(days=10).total_seconds())
    await mark_subscribed(mongo_db, CHANNEL, lease_seconds=ten_days)

    assert await due_for_renewal(mongo_db, now=now) == []
    doc = await mongo_db[STREAMERS].find_one({"channel_id": CHANNEL})
    assert doc is not None
    assert doc["websub_expires_at"] > now + dt.timedelta(days=9)


async def test_kenh_twitch_khong_lot_vao_danh_sach_gia_han_youtube(mongo_db: Db) -> None:
    await mongo_db[STREAMERS].insert_one(
        {"platform": "twitch", "channel_id": "kenh-twitch", "websub_expires_at": None}
    )

    assert await due_for_renewal(mongo_db) == []
