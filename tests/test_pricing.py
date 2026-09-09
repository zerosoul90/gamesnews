"""Ghi nhận giá — `app/services/pricing.py`.

Trọng tâm là cờ `is_historical_low`. Nó là thứ `/deals` sắp xếp theo, là thứ
điều kiện cảnh báo `historical_low` kích hoạt theo, và là dòng chữ "Đáy lịch
sử" hiện trên thẻ game. Sai nó thì cả ba chỗ cùng nói dối một lúc.
"""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.price import PriceCurrent
from app.services.pricing import mark_region_locked, record_prices

Db = AsyncIOMotorDatabase[dict[str, Any]]


@pytest.fixture
def game_id() -> ObjectId:
    """Một `_id` game mới cho mỗi test — `price_current` định danh theo nó."""
    return ObjectId()


def price(
    game_id: ObjectId, final: int, *, initial: int = 100_000, discount: int = 0
) -> PriceCurrent:
    return PriceCurrent(
        game_id=game_id,
        store="steam",
        price_initial=initial,
        price_final=final,
        discount_percent=discount,
    )


async def current(db: Db, game_id: ObjectId) -> dict[str, Any]:
    doc = await db.price_current.find_one({"game_id": game_id})
    assert doc is not None
    return doc


async def test_luot_quet_dau_tien_khong_duoc_bao_day_lich_su(
    mongo_db: Db, game_id: ObjectId
) -> None:
    """Chốt quan trọng nhất của file này.

    Ở lượt đầu, `lowest_ever` chính là giá vừa đọc, nên `price_final <=
    lowest_ever` luôn đúng. Bản trước vì thế gắn cờ đáy cho TOÀN BỘ catalog
    ngay lượt chạy đầu — tức là đúng lúc bắt đầu test thật thì mọi game đều
    hiện "Đáy lịch sử".
    """
    await record_prices(mongo_db, [price(game_id, 500_000, discount=30)])

    doc = await current(mongo_db, game_id)
    assert doc["is_historical_low"] is False
    assert doc["lowest_ever"] == 500_000
    assert doc["observations"] == 1


async def test_lan_quan_sat_thu_hai_moi_duoc_khang_dinh_day(
    mongo_db: Db, game_id: ObjectId
) -> None:
    """Và nó tự lành ở lượt sau, không kẹt False mãi mãi."""
    await record_prices(mongo_db, [price(game_id, 500_000)])
    await record_prices(mongo_db, [price(game_id, 500_000)])

    doc = await current(mongo_db, game_id)
    assert doc["is_historical_low"] is True
    assert doc["observations"] == 2


async def test_gia_tang_len_thi_mat_co_day_nhung_giu_lowest_ever(
    mongo_db: Db, game_id: ObjectId
) -> None:
    await record_prices(mongo_db, [price(game_id, 300_000)])
    await record_prices(mongo_db, [price(game_id, 300_000)])
    await record_prices(mongo_db, [price(game_id, 900_000)])

    doc = await current(mongo_db, game_id)
    assert doc["is_historical_low"] is False
    assert doc["lowest_ever"] == 300_000


async def test_gia_moi_thap_hon_thi_day_moi(mongo_db: Db, game_id: ObjectId) -> None:
    await record_prices(mongo_db, [price(game_id, 800_000)])
    await record_prices(mongo_db, [price(game_id, 200_000, discount=75)])

    doc = await current(mongo_db, game_id)
    assert doc["lowest_ever"] == 200_000
    assert doc["is_historical_low"] is True


async def test_game_free_khong_bao_gio_la_day_lich_su(mongo_db: Db, game_id: ObjectId) -> None:
    """Giá 0 là F2P, không phải một đợt giảm giá lịch sử."""
    await record_prices(mongo_db, [price(game_id, 0, initial=0)])
    await record_prices(mongo_db, [price(game_id, 0, initial=0)])

    doc = await current(mongo_db, game_id)
    assert doc["is_historical_low"] is False


async def test_gia_khong_doi_thi_khong_ghi_them_dong_lich_su(
    mongo_db: Db, game_id: ObjectId
) -> None:
    """Checkpoint PHASE-2: "không có dòng history trùng"."""
    first = await record_prices(mongo_db, [price(game_id, 400_000, discount=20)])
    second = await record_prices(mongo_db, [price(game_id, 400_000, discount=20)])

    assert first["history_added"] == 1
    assert second["history_added"] == 0
    assert await mongo_db.price_history.count_documents({"game_id": game_id}) == 1


async def test_doi_phan_tram_giam_cung_tinh_la_doi_gia(mongo_db: Db, game_id: ObjectId) -> None:
    """Cùng giá cuối nhưng % khác nghĩa là giá gốc đã đổi — vẫn phải ghi."""
    await record_prices(mongo_db, [price(game_id, 400_000, discount=20)])
    result = await record_prices(mongo_db, [price(game_id, 400_000, discount=50)])

    assert result["history_added"] == 1


async def test_khong_sinh_dong_price_current_trung(mongo_db: Db, game_id: ObjectId) -> None:
    for _ in range(3):
        await record_prices(mongo_db, [price(game_id, 100_000)])

    assert await mongo_db.price_current.count_documents({"game_id": game_id}) == 1


async def test_lo_rong_khong_lam_gi(mongo_db: Db) -> None:
    assert await record_prices(mongo_db, []) == {"updated": 0, "history_added": 0}


async def test_danh_dau_khoa_vung(mongo_db: Db) -> None:
    ids = [ObjectId(), ObjectId()]
    await mongo_db.games.insert_many([{"_id": ids[0]}, {"_id": ids[1]}])

    assert await mark_region_locked(mongo_db, ids) == 2
    assert await mark_region_locked(mongo_db, []) == 0

    doc = await mongo_db.games.find_one({"_id": ids[0]})
    assert doc is not None
    assert doc["region_locked_vn"] is True
