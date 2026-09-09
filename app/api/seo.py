"""Ảnh thẻ chia sẻ sinh phía server — `docs/PHASE-4.md`.

Checkpoint của Phase 4 là "thẻ chia sẻ render đúng trên Facebook và Zalo", nên
ảnh này là thứ **công khai nhất** của cả hệ thống: nó xuất hiện trên tường của
người khác, kèm tên miền của ta.

Vì vậy bản trước là chỗ mock nguy hiểm nhất trong dự án dù trông vô hại: nó vẽ
`price = "595.000 VND"` và `discount = "-30%"` viết cứng cho **mọi** game. Tức
là mỗi lần ai đó chia sẻ một trang game, hệ thống tự đăng một mức giá bịa lên
Facebook. Sai kiểu này không có log nào, không có test nào bắt được, và người
phát hiện đầu tiên sẽ là người dùng.

Nay giá lấy từ `price_current`. Không có giá thì vẽ thẻ không có giá — thiếu
thông tin thì thôi, đừng bịa.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.core.deps import MongoDep
from app.services.catalog import games

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:  # pragma: no cover - phụ thuộc vào môi trường cài đặt
    HAS_PIL = False

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["SEO"])

# Kích thước chuẩn thẻ OpenGraph cho Facebook và Zalo.
CARD_SIZE = (1200, 630)
BACKGROUND = (15, 23, 42)


def format_vnd(amount: int) -> str:
    """1090000 -> "1.090.000₫". Dấu chấm ngăn nghìn, đúng cách viết ở VN."""
    return f"{amount:,}".replace(",", ".") + "₫"


async def _card_data(db: Any, slug: str) -> dict[str, Any] | None:
    """Tên và giá thật của một game. None nếu không có game đó."""
    doc = await games(db).find_one({"slug": slug}, {"titles": 1})
    if doc is None:
        return None

    titles = doc.get("titles") or {}
    card: dict[str, Any] = {
        # Tên tiếng Việt nếu có: thẻ này để người Việt nhìn thấy.
        "name": titles.get("vi") or titles.get("primary") or slug,
        "price": None,
        "discount": None,
    }

    price = await db.price_current.find_one(
        {"game_id": doc["_id"], "store": "steam", "region": "vn"}
    )
    if price:
        final = price.get("price_final")
        if isinstance(final, int) and final > 0:
            card["price"] = format_vnd(final)
        discount = price.get("discount_percent") or 0
        if discount > 0:
            card["discount"] = f"-{discount}%"
    return card


@router.get("/og-image", response_class=Response)
async def generate_og_image(db: MongoDep, game: str) -> Response:
    """Ảnh OpenGraph cho một trang game, sinh từ dữ liệu thật."""
    if not HAS_PIL:
        raise HTTPException(
            status_code=501, detail="Tính năng sinh ảnh chưa được kích hoạt trên server"
        )

    card = await _card_data(db, game)
    if card is None:
        # 404 chứ không vẽ thẻ rỗng: một thẻ mang tên game không tồn tại vẫn
        # được Facebook cache lại và hiện suốt.
        raise HTTPException(status_code=404, detail="Không có game này")

    try:
        img = Image.new("RGB", CARD_SIZE, color=BACKGROUND)
        draw = ImageDraw.Draw(img)

        # Còn nợ: font mặc định của Pillow là bitmap, chữ rất nhỏ và **không có
        # dấu tiếng Việt**. Muốn thẻ dùng được thật thì phải kèm một file .ttf
        # hỗ trợ Unicode vào image Docker rồi load ở đây.
        font = ImageFont.load_default()

        draw.text((50, 100), card["name"], fill=(255, 255, 255), font=font)
        if card["discount"]:
            draw.text((50, 200), f"GIAM GIA: {card['discount']}", fill=(248, 113, 113), font=font)
        if card["price"]:
            draw.text((50, 250), f"GIA: {card['price']}", fill=(74, 222, 128), font=font)
        draw.text((50, 500), "GameNews.vn", fill=(148, 163, 184), font=font)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
    except Exception as exc:
        logger.exception("lỗi sinh ảnh chia sẻ")
        raise HTTPException(status_code=500, detail="Lỗi tạo ảnh") from exc

    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        # Cache một ngày: Facebook gọi lại rất nhiều lần cho cùng một link.
        headers={"Cache-Control": "public, max-age=86400"},
    )
