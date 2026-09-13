"""Chọn game để nhúng — `app/jobs/embeddings.py`.

Job này từng quét tuần tự cả `games`, theo đúng chữ trong tài liệu: "một đợt
nạp vector cho toàn catalog". Đo thật ngày 2026-09-13 cho thấy điều đó bất
khả với hạn mức miễn phí — ~100 content/phút, tức 31 ngày quota thuần cho
185.231 game — và tệ hơn, nó vét mất hạn mức mà `crawl_all_sources` cần để
dịch tin.

Nên thứ đáng kiểm ở đây không phải "có nhúng được không" mà là **nhúng đúng
game nào trước**.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.jobs.embeddings import MIN_REVIEWS_FOR_EMBEDDING, _as_object_ids, _candidates
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def add_game(db: Db, slug: str, name: str) -> ObjectId:
    await upsert_game(
        db,
        with_aliases(
            Game(
                slug=slug,
                titles=Titles(primary=name),
                external_ids=ExternalIds(steam_appid=abs(hash(slug)) % 10**6),
            )
        ),
        key="steam_appid",
    )
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    game_id: ObjectId = doc["_id"]
    return game_id


def names(batch: list[dict[str, Any]]) -> set[str]:
    return {(doc.get("titles") or {}).get("primary", "") for doc in batch}


def test_ep_kieu_game_id_nhan_ca_chuoi_lan_objectid() -> None:
    """`game_hotness` và `articles` lưu chuỗi, `game_reviews` lưu ObjectId.

    Tra bằng sai kiểu thì truy vấn không lỗi, nó chỉ lặng lẽ không khớp gì —
    đúng cách cảnh báo giá từng đứt mà không ai thấy.
    """
    oid = ObjectId()

    assert _as_object_ids([oid]) == [oid]
    assert _as_object_ids([str(oid)]) == [oid]
    assert _as_object_ids(["không-phải-id", None, 12, ""]) == []


async def test_game_vo_danh_khong_duoc_nhung(mongo_db: Db) -> None:
    """Chốt chính: catalog đầy game chưa ai từng viết bài về nó."""
    await add_game(mongo_db, "game-vo-danh", "Game Vô Danh")

    assert await _candidates(mongo_db, 10) == []


async def test_uu_tien_game_da_tung_len_tin(mongo_db: Db) -> None:
    """Đã được nhắc một lần thì sẽ được nhắc lại — và lần sau có thể không kèm
    link store (tầng 1 trượt) cũng không trùng alias nào (tầng 2 trượt)."""
    game_id = await add_game(mongo_db, "da-len-tin", "Đã Lên Tin")
    await add_game(mongo_db, "game-vo-danh", "Game Vô Danh")
    # `articles` lưu `game_id` dưới dạng chuỗi, đúng như job tin thật ghi.
    await mongo_db.articles.insert_one({"url": "https://x/1", "game_id": str(game_id)})

    assert names(await _candidates(mongo_db, 10)) == {"Đã Lên Tin"}


async def test_uu_tien_game_trong_bang_hot(mongo_db: Db) -> None:
    game_id = await add_game(mongo_db, "dang-hot", "Đang Hot")
    await mongo_db.game_hotness.insert_one({"game_id": str(game_id), "ccu_now": 18714})

    assert names(await _candidates(mongo_db, 10)) == {"Đang Hot"}


async def test_duoi_nguong_review_thi_khong_nhung(mongo_db: Db) -> None:
    game_id = await add_game(mongo_db, "it-nguoi-choi", "Ít Người Chơi")
    await mongo_db.game_reviews.insert_one(
        {"game_id": game_id, "total": MIN_REVIEWS_FOR_EMBEDDING - 1}
    )

    assert await _candidates(mongo_db, 10) == []


async def test_nhieu_review_nhat_di_truoc(mongo_db: Db) -> None:
    """Quota chỉ đủ một phần thì phần được nạp phải là phần đáng nạp."""
    for slug, name, total in (
        ("noi-tieng", "Nổi Tiếng", 1_154_113),
        ("kha-noi-tieng", "Khá Nổi Tiếng", 20_000),
        ("vua-du-nguong", "Vừa Đủ Ngưỡng", MIN_REVIEWS_FOR_EMBEDDING),
    ):
        game_id = await add_game(mongo_db, slug, name)
        await mongo_db.game_reviews.insert_one({"game_id": game_id, "total": total})

    batch = await _candidates(mongo_db, 2)

    assert [(doc.get("titles") or {}).get("primary") for doc in batch] == [
        "Nổi Tiếng",
        "Khá Nổi Tiếng",
    ]


async def test_game_da_co_vector_khong_nhung_lai(mongo_db: Db) -> None:
    """Mỗi lần embed là một lần tiêu quota; nạp lại thứ không đổi là đổ đi."""
    game_id = await add_game(mongo_db, "da-co-vector", "Đã Có Vector")
    await mongo_db.game_reviews.insert_one({"game_id": game_id, "total": 900_000})
    await games(mongo_db).update_one({"_id": game_id}, {"$set": {"embedding_hash": "abc123"}})

    assert await _candidates(mongo_db, 10) == []


async def test_khong_tra_ve_game_trung_giua_hai_nguon(mongo_db: Db) -> None:
    """Một game vừa lên tin vừa nhiều review thì vẫn chỉ nhúng một lần."""
    game_id = await add_game(mongo_db, "ca-hai", "Cả Hai")
    await mongo_db.articles.insert_one({"url": "https://x/2", "game_id": str(game_id)})
    await mongo_db.game_reviews.insert_one({"game_id": game_id, "total": 900_000})

    batch = await _candidates(mongo_db, 10)

    assert len(batch) == 1
