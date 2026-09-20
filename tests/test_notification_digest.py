"""Job gom digest — `app/jobs/notification_digest.py`.

Trước file này job chỉ được kiểm **có tên trong lịch cron** (`test_worker_schedule`),
còn hành vi thì không test nào chạm tới. Mà đây lại là nơi cuối cùng của đường
thông báo: mọi cảnh báo rơi vào `notification_queue` đều phải đi qua đây mới tới
được người dùng.

Hai bất biến dưới đây đều đã từng hỏng và đều hỏng **im lặng**:

- Gửi không tới mà vẫn xoá hàng đợi → thông báo biến mất, không ai biết.
- `delete_many({})` → xoá cả thông báo của user khác, kể cả cái vừa được chèn
  vào sau lúc `aggregate` chạy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.jobs import notification_digest
from app.jobs.notification_digest import send_notification_digest

Db = AsyncIOMotorDatabase[dict[str, Any]]


@dataclass
class ClientsGia:
    db: Db
    http: httpx.AsyncClient | None = None


def ctx_cua(db: Db) -> dict[str, Any]:
    return {"clients": ClientsGia(db=db)}


async def xep_hang(db: Db, user_id: ObjectId, title: str, loai: str = "price_alert") -> None:
    await db.notification_queue.insert_one(
        {"user_id": user_id, "type": loai, "title": title, "body": title, "data": {}}
    )


async def test_hang_doi_rong_thi_khong_lam_gi(mongo_db: Db) -> None:
    ket_qua = await send_notification_digest(ctx_cua(mongo_db))

    assert ket_qua == {"users_processed": 0, "notifications_sent": 0}


async def test_gui_khong_toi_thi_van_giu_hang_doi(mongo_db: Db) -> None:
    """FCM chưa cấu hình → `send_push_notification` trả 0 → phải giữ lại.

    Không cần giả lập gì: ở môi trường test FCM vốn không có khoá, nên đây là
    đúng đường chạy thật. Xoá đi là mất hẳn thông báo mà không ai biết — và
    người dùng thì đã đặt cảnh báo ấy bằng tay.
    """
    user_id = ObjectId()
    await xep_hang(mongo_db, user_id, "Giảm giá Elden Ring")

    ket_qua = await send_notification_digest(ctx_cua(mongo_db))

    assert ket_qua["notifications_sent"] == 0
    assert await mongo_db.notification_queue.count_documents({"user_id": user_id}) == 1


async def test_gui_duoc_thi_chi_xoa_phan_cua_chinh_user_do(
    mongo_db: Db, monkeypatch: Any
) -> None:
    """Bất biến quan trọng nhất của job này.

    Bản trước gọi `delete_many({})`. Với một user thì nó *trông* đúng — nên chỉ
    test có từ hai user trở lên mới bắt được.
    """
    toi = ObjectId()
    nguoi_khac = ObjectId()
    await xep_hang(mongo_db, toi, "Deal 1")
    await xep_hang(mongo_db, toi, "Deal 2")
    await xep_hang(mongo_db, nguoi_khac, "Deal cua nguoi khac")

    da_gui: list[tuple[ObjectId, str]] = []

    async def gui_gia(
        db: Db, http: Any, user_id: ObjectId, title: str, body: str, data: Any
    ) -> int:
        # Chỉ user `toi` gửi được; user kia hỏng. Một lượt job phải xử lý đúng
        # cả hai kết cục cùng lúc.
        da_gui.append((user_id, title))
        return 1 if user_id == toi else 0

    monkeypatch.setattr(notification_digest, "send_push_notification", gui_gia)

    ket_qua = await send_notification_digest(ctx_cua(mongo_db))

    assert ket_qua["users_processed"] == 1
    assert ket_qua["notifications_sent"] == 2

    # Hàng đợi của tôi sạch, của người khác còn nguyên.
    assert await mongo_db.notification_queue.count_documents({"user_id": toi}) == 0
    assert await mongo_db.notification_queue.count_documents({"user_id": nguoi_khac}) == 1


async def test_gom_nhieu_thong_bao_thanh_mot_digest(mongo_db: Db, monkeypatch: Any) -> None:
    """Ba thông báo → **một** lần gửi, và tiêu đề nói đúng con số.

    Gửi ba lần riêng lẻ thì đúng là cái digest sinh ra để tránh.
    """
    user_id = ObjectId()
    for i in range(3):
        await xep_hang(mongo_db, user_id, f"Deal {i}")

    lan_gui: list[tuple[str, str]] = []

    async def gui_gia(db: Db, http: Any, uid: ObjectId, title: str, body: str, data: Any) -> int:
        lan_gui.append((title, body))
        return 1

    monkeypatch.setattr(notification_digest, "send_push_notification", gui_gia)

    await send_notification_digest(ctx_cua(mongo_db))

    assert len(lan_gui) == 1
    title, body = lan_gui[0]
    assert "3" in title
    assert "2 tin khác" in body


async def test_mot_thong_bao_thi_khong_noi_them_tin_khac(
    mongo_db: Db, monkeypatch: Any
) -> None:
    """Đúng một thông báo thì không được thòng "và 0 tin khác"."""
    user_id = ObjectId()
    await xep_hang(mongo_db, user_id, "Deal duy nhat")

    than: list[str] = []

    async def gui_gia(db: Db, http: Any, uid: ObjectId, title: str, body: str, data: Any) -> int:
        than.append(body)
        return 1

    monkeypatch.setattr(notification_digest, "send_push_notification", gui_gia)

    await send_notification_digest(ctx_cua(mongo_db))

    assert "tin khác" not in than[0]
