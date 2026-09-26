"""Ảnh thẻ chia sẻ — `docs/PHASE-4.md`.

Đây là thứ công khai nhất của hệ thống: nó lên tường Facebook của người khác
kèm tên miền của ta. Nên test tập trung vào một câu hỏi: **có bịa số nào
không.**
"""

from __future__ import annotations

import io
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


# --- Font ảnh thẻ chia sẻ ------------------------------------------------------


def test_co_font_du_dau_tieng_viet() -> None:
    """Font mặc định của Pillow không có "ặ" và "₫" — thẻ Facebook ra ô vuông.

    Không chỉ kiểm file tồn tại: so ảnh của từng ký tự với ảnh của một ký tự
    chắc chắn KHÔNG có trong font (vùng riêng tư Unicode). Font thiếu chữ nào
    thì chữ đó vẽ ra đúng cái ô "không có" ấy.
    """
    from PIL import Image, ImageDraw

    from app.api.seo import _font, font_path

    assert font_path(bold=False) is not None
    assert font_path(bold=True) is not None

    def ve(font: object, chu: str) -> bytes:
        img = Image.new("L", (120, 120))
        ImageDraw.Draw(img).text((10, 10), chu, fill=255, font=font)  # type: ignore[arg-type]
        return img.tobytes()

    for bold in (False, True):
        font = _font(64, bold=bold)
        khong_co = ve(font, "\U000f0000")
        for chu in ("ặ", "ữ", "Đ", "₫"):
            assert ve(font, chu) != khong_co, (chu, bold)


def test_ten_dai_duoc_ngat_dong_va_cat() -> None:
    """Đo bằng pixel của chính font, không đếm ký tự: bản đầu ngắt ở 30 ký tự
    và "The Witcher 3: Săn Lùng Dã Thú" tràn mất chữ cuối ở mép phải."""
    from app.api.seo import TEXT_MAX_WIDTH, TITLE_MAX_LINES, TITLE_SIZE, _font, title_lines

    font = _font(TITLE_SIZE, bold=True)
    assert title_lines("Elden Ring", font) == ["Elden Ring"]

    witcher = title_lines("The Witcher 3: Săn Lùng Dã Thú", font)
    assert " ".join(witcher) == "The Witcher 3: Săn Lùng Dã Thú"
    assert all(font.getlength(line) <= TEXT_MAX_WIDTH for line in witcher)

    dai = title_lines(
        "The Witcher 3: Săn Lùng Dã Thú - Phiên Bản Đầy Đủ Mọi Bản Mở Rộng, "
        "Kèm Nhạc Nền, Artbook Và Toàn Bộ Nội Dung Tải Thêm Từ Ngày Phát Hành",
        font,
    )
    assert len(dai) == TITLE_MAX_LINES
    assert all(font.getlength(line) <= TEXT_MAX_WIDTH for line in dai)
    assert dai[-1].endswith("…")

    # Một "từ" dài hơn cả dòng vẫn không được tràn.
    viet_lien = title_lines("A" * 80, font)
    assert all(font.getlength(line) <= TEXT_MAX_WIDTH for line in viet_lien)


async def test_anh_the_dung_kich_thuoc_opengraph(mongo_db: Db) -> None:
    from PIL import Image

    from app.api.seo import CARD_SIZE, generate_og_image

    await mongo_db.games.insert_one(
        {"slug": "game-thu", "titles": {"primary": "Game Thử", "vi": "Săn Lùng Dã Thú"}}
    )
    res = await generate_og_image(mongo_db, "game-thu")

    assert res.media_type == "image/png"
    img = Image.open(io.BytesIO(bytes(res.body)))
    assert img.size == CARD_SIZE
