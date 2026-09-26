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


def ngoai_gio_im_lang(monkeypatch: Any) -> None:
    """Ghim "đang ngoài giờ im lặng" cho test đi qua `process_notification`.

    **Vì sao cần.** Hàm ấy đọc `dt.datetime.now(dt.UTC)` rồi quy ra giờ VN, nên
    ba test dưới đây phụ thuộc vào *lúc* chúng chạy. Hậu quả đo được:

    - `test_gui_ngay_toi_noi_thi_khong_xep_hang` **đỏ từ 22:00 tới 07:00 giờ
      VN**, tức 9 tiếng mỗi ngày. Trong khung đó `wants_immediate` là False nên
      `send_push_notification` không hề được gọi, thông báo xuống hàng đợi
      digest — đúng thiết kế — và assert `== 0` gãy.
    - Hai test kia vẫn xanh nhưng **rỗng nghĩa** trong cùng khung giờ: cả nhánh
      chúng muốn kiểm lẫn nhánh giờ im lặng đều kết thúc bằng một dòng trong
      hàng đợi, nên con số 1 không phân biệt được hai đường.

    Đỏ nửa ngày thì còn thấy; xanh rỗng nghĩa nửa ngày mới là phần đáng sợ.

    Vá đúng chỗ này chứ không ghim đồng hồ toàn cục: bản thân
    `is_in_quiet_hours` đã có test riêng ở cuối file với mốc giờ cố định, nên
    chắn nó ở đây không mất độ phủ nào.
    """
    from app.services import notification as mod

    monkeypatch.setattr(mod, "is_in_quiet_hours", lambda *a, **k: False)


async def test_thieu_http_thi_vao_hang_doi_chu_khong_bien_mat(
    mongo_db: Db, monkeypatch: Any
) -> None:
    ngoai_gio_im_lang(monkeypatch)
    user_id = await make_user(mongo_db)

    await process_notification(mongo_db, alert(user_id), http=None)

    assert await mongo_db.notification_queue.count_documents({"user_id": user_id}) == 1


async def test_gui_ngay_khong_toi_thi_vao_hang_doi_chu_khong_bien_mat(
    mongo_db: Db, monkeypatch: Any
) -> None:
    """Biến thể thứ hai của cùng một lỗi: **có** http client, nhưng gửi trả 0.

    Bản trước `return` vô điều kiện sau `send_push_notification`, nên mọi lượt
    không gửi được — FCM chưa cấu hình, user chưa có thiết bị, hay cả loạt
    token đều chết — đều đánh rơi thông báo, để lại đúng một dòng log.

    Đo được trên stack thật (2026-09-20): FCM chưa có khoá, cảnh báo
    `below_price` khớp đúng điều kiện, và sau đó nó không nằm ở
    `notification_queue` lẫn bất cứ đâu. Đây là trạng thái mặc định của dự án
    lúc này, không phải một ca hiếm.
    """
    import httpx

    from app.services import notification as mod

    ngoai_gio_im_lang(monkeypatch)
    user_id = await make_user(mongo_db)

    async def khong_gui_duoc(*args: Any, **kwargs: Any) -> int:
        return 0

    monkeypatch.setattr(mod, "send_push_notification", khong_gui_duoc)

    async with httpx.AsyncClient() as http:
        await process_notification(mongo_db, alert(user_id), http=http)

    assert await mongo_db.notification_queue.count_documents({"user_id": user_id}) == 1


async def test_gui_ngay_toi_noi_thi_khong_xep_hang(mongo_db: Db, monkeypatch: Any) -> None:
    """Chiều ngược lại — thiếu nó thì mọi thông báo đều bị nhân đôi.

    Gửi thành công mà vẫn xếp hàng nghĩa là digest sẽ gửi lại lần nữa vào 2h
    sáng hôm sau.
    """
    import httpx

    from app.services import notification as mod

    ngoai_gio_im_lang(monkeypatch)
    user_id = await make_user(mongo_db)

    async def gui_duoc(*args: Any, **kwargs: Any) -> int:
        return 1

    monkeypatch.setattr(mod, "send_push_notification", gui_duoc)

    async with httpx.AsyncClient() as http:
        await process_notification(mongo_db, alert(user_id), http=http)

    assert await mongo_db.notification_queue.count_documents({"user_id": user_id}) == 0


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


async def test_tat_kenh_streamer_live_thi_khong_gui(mongo_db: Db) -> None:
    """Kênh này có trong model từ Phase 3 mà gatekeeper không đọc: tắt vẫn nhận.
    Lộ ra đúng lúc làm giao diện bật/tắt."""
    user_id = await make_user(mongo_db, {"channels": {"streamer_live": False}})
    payload = NotificationPayload(
        user_id=user_id, type="streamer_live", title="Đang live", body="...", data={}
    )

    await process_notification(mongo_db, payload, http=None)

    assert await mongo_db.notification_queue.count_documents({}) == 0
