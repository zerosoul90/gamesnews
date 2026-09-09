"""Gatekeeper thông báo — `app/services/notification.py`.

Kiểm đúng một đường đi từng đánh rơi thông báo trong im lặng: loại thông báo có
tư cách gửi tức thì, nhưng không có http client. Bản trước ghi một dòng log rồi
**rơi ra khỏi hàm** — nhánh `else` không chạy vì nhánh `if` đã được chọn — nên
thông báo không được gửi mà cũng không vào hàng đợi digest. Đúng cái sai mà
chú thích ngay chỗ đó tuyên bố là đã tránh.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.notification import (
    NotificationPayload,
    is_in_quiet_hours,
    process_notification,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def make_user(db: Db, settings: dict[str, Any] | None = None) -> ObjectId:
    user_id = ObjectId()
    await db.users.insert_one({"_id": user_id, "notification_settings": settings or {}})
    return user_id


def alert(user_id: ObjectId, **data: Any) -> NotificationPayload:
    return NotificationPayload(
        user_id=user_id, type="price_alert", title="Giảm giá", body="...", data=data
    )


async def test_thieu_http_thi_vao_hang_doi_chu_khong_bien_mat(mongo_db: Db) -> None:
    user_id = await make_user(mongo_db)

    await process_notification(mongo_db, alert(user_id), http=None)

    assert await mongo_db.notification_queue.count_documents({"user_id": user_id}) == 1


async def test_user_khong_ton_tai_thi_khong_ghi_gi(mongo_db: Db) -> None:
    await process_notification(mongo_db, alert(ObjectId()), http=None)
    assert await mongo_db.notification_queue.count_documents({}) == 0


async def test_kenh_bi_tat_thi_khong_gui(mongo_db: Db) -> None:
    user_id = await make_user(mongo_db, {"channels": {"price_alert": False}})

    await process_notification(mongo_db, alert(user_id), http=None)

    assert await mongo_db.notification_queue.count_documents({}) == 0


async def test_khong_bao_giam_gia_game_da_so_huu(mongo_db: Db) -> None:
    """Ranh giới không được vượt của `CLAUDE.md`."""
    user_id = await make_user(mongo_db)
    game_id = ObjectId()
    await mongo_db.user_library.insert_one({"user_id": user_id, "game_id": game_id})

    await process_notification(mongo_db, alert(user_id, game_id=str(game_id)), http=None)

    assert await mongo_db.notification_queue.count_documents({}) == 0


async def test_game_khong_so_huu_thi_van_bao(mongo_db: Db) -> None:
    user_id = await make_user(mongo_db)

    await process_notification(mongo_db, alert(user_id, game_id=str(ObjectId())), http=None)

    assert await mongo_db.notification_queue.count_documents({}) == 1


async def test_game_id_hong_thi_fail_closed(mongo_db: Db) -> None:
    """Không kiểm được thư viện thì im lặng bỏ qua, không phải cứ gửi."""
    user_id = await make_user(mongo_db)

    await process_notification(mongo_db, alert(user_id, game_id="không-phải-objectid"), http=None)

    assert await mongo_db.notification_queue.count_documents({}) == 0


# --- Giờ im lặng -----------------------------------------------------------


def at(hour: int, minute: int = 0) -> dt.datetime:
    """Một mốc UTC ứng với giờ VN cho trước (GMT+7)."""
    return dt.datetime(2026, 9, 9, hour, minute, tzinfo=dt.UTC) - dt.timedelta(hours=7)


def test_khoang_qua_dem() -> None:
    assert is_in_quiet_hours(at(23), "22:00", "07:00") is True
    assert is_in_quiet_hours(at(3), "22:00", "07:00") is True
    assert is_in_quiet_hours(at(12), "22:00", "07:00") is False


def test_khoang_trong_ngay() -> None:
    assert is_in_quiet_hours(at(13), "12:00", "14:00") is True
    assert is_in_quiet_hours(at(15), "12:00", "14:00") is False


def test_gio_sai_dinh_dang_thi_coi_nhu_khong_im_lang() -> None:
    """Cấu hình hỏng không được biến thành "chặn hết mọi thông báo"."""
    assert is_in_quiet_hours(at(23), "hai mươi hai giờ", "07:00") is False
