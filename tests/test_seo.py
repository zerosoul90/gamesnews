"""Ảnh thẻ chia sẻ — `docs/PHASE-4.md`.

Đây là thứ công khai nhất của hệ thống: nó lên tường Facebook của người khác
kèm tên miền của ta. Nên test tập trung vào một câu hỏi: **có bịa số nào
không.**
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.seo import _card_data, format_vnd
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]


def test_dinh_dang_tien_viet() -> None:
    assert format_vnd(1090000) == "1.090.000₫"
    assert format_vnd(595000) == "595.000₫"
    assert format_vnd(0) == "0₫"


async def add(db: Db, slug: str, primary: str, vi: str | None = None) -> Any:
    await ensure_indexes(db)
    game = with_aliases(
        Game(
            slug=slug,
            titles=Titles(primary=primary, vi=vi),
            external_ids=ExternalIds(steam_appid=abs(hash(slug)) % 10**6),
        )
    )
    await upsert_game(db, game, key="steam_appid")
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    return doc["_id"]


async def test_khong_co_gia_thi_khong_bia_gia(mongo_db: Db) -> None:
    """Bản trước vẽ "595.000 VND" viết cứng cho MỌI game, tức mỗi lần ai chia
    sẻ là hệ thống tự đăng một mức giá bịa lên Facebook."""
    await add(mongo_db, "game-chua-co-gia", "Game Chưa Có Giá")

    card = await _card_data(mongo_db, "game-chua-co-gia")

    assert card is not None
    assert card["price"] is None
    assert card["discount"] is None


async def test_lay_dung_gia_that_tu_price_current(mongo_db: Db) -> None:
    game_id = await add(mongo_db, "elden-ring", "Elden Ring")
    await mongo_db.price_current.insert_one(
        {
            "game_id": game_id,
            "store": "steam",
            "region": "vn",
            "price_final": 693000,
            "discount_percent": 30,
        }
    )

    card = await _card_data(mongo_db, "elden-ring")

    assert card is not None
    assert card["price"] == "693.000₫"
    assert card["discount"] == "-30%"


async def test_giam_0_phan_tram_thi_khong_ve_nhan_giam_gia(mongo_db: Db) -> None:
    game_id = await add(mongo_db, "game-nguyen-gia", "Game Nguyên Giá")
    await mongo_db.price_current.insert_one(
        {
            "game_id": game_id,
            "store": "steam",
            "region": "vn",
            "price_final": 500000,
            "discount_percent": 0,
        }
    )

    card = await _card_data(mongo_db, "game-nguyen-gia")

    assert card is not None
    assert card["price"] == "500.000₫"
    assert card["discount"] is None


async def test_uu_tien_ten_tieng_viet(mongo_db: Db) -> None:
    """Thẻ này để người Việt nhìn thấy."""
    await add(mongo_db, "arena-of-valor", "Arena of Valor", vi="Liên Quân Mobile")

    card = await _card_data(mongo_db, "arena-of-valor")

    assert card is not None
    assert card["name"] == "Liên Quân Mobile"


async def test_game_khong_ton_tai_thi_tra_none(mongo_db: Db) -> None:
    """Endpoint trả 404 chứ không vẽ thẻ rỗng: một thẻ mang tên game không có
    thật vẫn bị Facebook cache lại và hiện suốt."""
    await ensure_indexes(mongo_db)

    assert await _card_data(mongo_db, "khong-ton-tai") is None
