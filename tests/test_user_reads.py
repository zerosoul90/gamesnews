"""Đường đọc dữ liệu cá nhân hoá — `app/services/user_reads.py`.

Trước lượt này nhóm `/api/v1/user` chỉ có đường ghi, nên ba màn giao diện bị
chặn ở backend chứ không phải ở web.

Trọng tâm: **phân quyền khi xoá**. Xoá theo `_id` trần mà quên kẹp `user_id` là
lỗ hổng im lặng — không lỗi nào nổi lên, chỉ có dữ liệu của người khác biến mất.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user import PriceAlert, UserFollow, UserLibrary
from app.services.user_reads import (
    alerts_of,
    delete_alert,
    delete_follow,
    follows_of,
    library_of,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def add_game(db: Db, slug: str, title: str = "Elden Ring") -> ObjectId:
    res = await db.games.insert_one(
        {"slug": slug, "titles": {"primary": title}, "media": {"cover": f"https://img/{slug}.jpg"}}
    )
    return ObjectId(res.inserted_id)


async def own(db: Db, user_id: ObjectId, game_id: ObjectId, phut: int = 60) -> None:
    lib = UserLibrary(
        user_id=user_id,
        store="steam",
        game_id=game_id,
        playtime_minutes=phut,
        synced_at="2026-09-17T00:00:00+00:00",
    )
    await db.user_library.insert_one(lib.to_mongo())


async def add_alert(db: Db, user_id: ObjectId, game_id: ObjectId, value: int = 200_000) -> ObjectId:
    alert = PriceAlert(user_id=user_id, game_id=game_id, condition="below_price", value=value)
    res = await db.price_alerts.insert_one(alert.to_mongo())
    return ObjectId(res.inserted_id)


# --- thư viện ----------------------------------------------------------------


async def test_thu_vien_choi_nhieu_nhat_truoc(mongo_db: Db) -> None:
    me = ObjectId()
    it = await add_game(mongo_db, "it", "Ít giờ")
    nhieu = await add_game(mongo_db, "nhieu", "Nhiều giờ")
    await own(mongo_db, me, it, 10)
    await own(mongo_db, me, nhieu, 500)

    items, total = await library_of(mongo_db, me)

    assert total == 2
    assert [i["game"]["title"] for i in items] == ["Nhiều giờ", "Ít giờ"]
    assert items[0]["playtime_minutes"] == 500


async def test_thu_vien_chi_tra_cua_minh(mongo_db: Db) -> None:
    """Thiếu điều kiện `user_id` thì mọi người dùng nhìn thấy thư viện của nhau."""
    me, nguoi_khac = ObjectId(), ObjectId()
    g1, g2 = await add_game(mongo_db, "a"), await add_game(mongo_db, "b")
    await own(mongo_db, me, g1)
    await own(mongo_db, nguoi_khac, g2)

    items, total = await library_of(mongo_db, me)

    assert total == 1
    assert items[0]["game_id"] == str(g1)


async def test_game_da_bi_xoa_khoi_catalog_thi_the_vang_mat(mongo_db: Db) -> None:
    """`game` là None chứ không phải dict rỗng — giao diện phân biệt được."""
    me = ObjectId()
    await own(mongo_db, me, ObjectId())

    items, _ = await library_of(mongo_db, me)

    assert items[0]["game"] is None


# --- cảnh báo giá ------------------------------------------------------------


async def test_canh_bao_cho_game_da_so_huu_van_tra_ve_kem_co_owned(mongo_db: Db) -> None:
    """Quyết định có chủ ý: KHÔNG giấu, mà gắn cờ.

    Chặn gửi thật nằm ở `notification.process_notification`. Giấu khỏi danh sách
    thì cảnh báo do chính người dùng đặt biến mất không lời giải thích, và họ
    đặt lại.
    """
    me = ObjectId()
    da_co = await add_game(mongo_db, "da-co")
    chua_co = await add_game(mongo_db, "chua-co")
    await own(mongo_db, me, da_co)
    await add_alert(mongo_db, me, da_co)
    await add_alert(mongo_db, me, chua_co)

    alerts = await alerts_of(mongo_db, me)

    theo_game = {a["game_id"]: a["owned"] for a in alerts}
    assert theo_game[str(da_co)] is True
    assert theo_game[str(chua_co)] is False
    assert len(alerts) == 2, "không được giấu cảnh báo của game đã sở hữu"


async def test_co_owned_khong_lan_sang_nguoi_khac(mongo_db: Db) -> None:
    """Người khác sở hữu game không làm cảnh báo của tôi thành `owned`."""
    me, nguoi_khac = ObjectId(), ObjectId()
    game = await add_game(mongo_db, "chung")
    await own(mongo_db, nguoi_khac, game)
    await add_alert(mongo_db, me, game)

    alerts = await alerts_of(mongo_db, me)

    assert alerts[0]["owned"] is False


async def test_canh_bao_chi_tra_cua_minh(mongo_db: Db) -> None:
    me, nguoi_khac = ObjectId(), ObjectId()
    game = await add_game(mongo_db, "g")
    await add_alert(mongo_db, me, game)
    await add_alert(mongo_db, nguoi_khac, game)

    assert len(await alerts_of(mongo_db, me)) == 1


# --- phân quyền khi xoá ------------------------------------------------------


async def test_khong_xoa_duoc_canh_bao_cua_nguoi_khac(mongo_db: Db) -> None:
    """Lỗ hổng kinh điển: xoá theo `_id` trần. Nó im lặng — không lỗi nào nổi
    lên, chỉ có dữ liệu của người khác biến mất."""
    me, nan_nhan = ObjectId(), ObjectId()
    game = await add_game(mongo_db, "g")
    cua_nan_nhan = await add_alert(mongo_db, nan_nhan, game)

    xoa_duoc = await delete_alert(mongo_db, me, cua_nan_nhan)

    assert xoa_duoc is False
    assert await mongo_db.price_alerts.count_documents({"_id": cua_nan_nhan}) == 1


async def test_xoa_duoc_canh_bao_cua_chinh_minh(mongo_db: Db) -> None:
    me = ObjectId()
    game = await add_game(mongo_db, "g")
    cua_toi = await add_alert(mongo_db, me, game)

    assert await delete_alert(mongo_db, me, cua_toi) is True
    assert await mongo_db.price_alerts.count_documents({"_id": cua_toi}) == 0


async def test_khong_xoa_duoc_theo_doi_cua_nguoi_khac(mongo_db: Db) -> None:
    me, nan_nhan = ObjectId(), ObjectId()
    game = await add_game(mongo_db, "g")
    f = UserFollow(user_id=nan_nhan, target_type="game", target_id=game)
    res = await mongo_db.user_follows.insert_one(f.to_mongo())

    xoa_duoc = await delete_follow(mongo_db, me, ObjectId(res.inserted_id))

    assert xoa_duoc is False
    assert await mongo_db.user_follows.count_documents({}) == 1


# --- theo dõi ----------------------------------------------------------------


async def test_theo_doi_game_gan_duoc_the_game(mongo_db: Db) -> None:
    me = ObjectId()
    game = await add_game(mongo_db, "elden-ring", "Elden Ring")
    f = UserFollow(user_id=me, target_type="game", target_id=game)
    await mongo_db.user_follows.insert_one(f.to_mongo())

    follows = await follows_of(mongo_db, me)

    assert follows[0]["target"]["title"] == "Elden Ring"
    assert follows[0]["target"]["slug"] == "elden-ring"


async def test_theo_doi_khong_phai_game_thi_target_la_none(mongo_db: Db) -> None:
    """`target_id` của streamer là chuỗi, không tra được thẻ game. `None` ở đây
    là bình thường, không phải lỗi."""
    me = ObjectId()
    f = UserFollow(user_id=me, target_type="streamer", target_id="pewdiepie")
    await mongo_db.user_follows.insert_one(f.to_mongo())

    follows = await follows_of(mongo_db, me)

    assert follows[0]["target"] is None
    assert follows[0]["target_id"] == "pewdiepie"
    assert follows[0]["target_type"] == "streamer"
