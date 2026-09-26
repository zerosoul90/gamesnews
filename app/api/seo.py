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

import functools
import io
import logging
from pathlib import Path
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

# Font có đủ dấu tiếng Việt và "₫", theo thứ tự thử. DejaVu cài trong
# Dockerfile và trên CI; Arial là của máy dev Windows.
#
# Trước đây dùng `ImageFont.load_default()`: bitmap, chữ cỡ ~11px trên nền
# 1200x630, và không có dấu — "Săn Lùng Dã Thú" ra thành "S?n L?ng D? Th?",
# "400.000₫" ra "400.000?". Đó là thứ hiện trên tường Facebook của người khác
# mỗi lần ai đó chia sẻ một trang game.
FONT_CANDIDATES: dict[bool, tuple[str, ...]] = {
    False: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ),
    True: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ),
}

TITLE_SIZE = 64
TITLE_MAX_LINES = 3
MARGIN_X = 60
# Bề rộng tối đa của một dòng chữ, tính bằng PIXEL. Bản đầu ngắt theo 30 ký tự
# và tên "The Witcher 3: Săn Lùng Dã Thú" (đúng 30 ký tự) tràn mất chữ "Thú" ở
# mép phải: DejaVu Bold rộng hơn Arial nhiều. Chỉ đo bằng chính font mới đúng.
TEXT_MAX_WIDTH = CARD_SIZE[0] - 2 * MARGIN_X


def font_path(bold: bool = False) -> str | None:
    """Đường dẫn font đầu tiên có thật, hoặc None."""
    return next((p for p in FONT_CANDIDATES[bold] if Path(p).is_file()), None)


@functools.cache
def _font(size: int, bold: bool = False) -> Any:
    path = font_path(bold)
    if path is None:
        # Không chết: thẻ xấu vẫn hơn không có thẻ. Nhưng ghi mức error — đây là
        # thứ phải sửa ở image, không phải bỏ qua.
        logger.error("không tìm thấy font có dấu tiếng Việt cho ảnh thẻ chia sẻ")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def title_lines(name: str, font: Any, max_width: int = TEXT_MAX_WIDTH) -> list[str]:
    """Tên game ngắt dòng theo bề rộng pixel đo bằng `font`, tối đa
    `TITLE_MAX_LINES` dòng; dư thì dòng cuối cắt bằng "…"."""

    def rong(text: str) -> float:
        return float(font.getlength(text))

    lines: list[str] = []
    for word in name.split():
        if lines and rong(f"{lines[-1]} {word}") <= max_width:
            lines[-1] = f"{lines[-1]} {word}"
            continue
        # Một từ đơn dài hơn cả dòng (hiếm, nhưng có tên viết liền) thì cắt cứng.
        while rong(word) > max_width:
            cut = len(word)
            while cut > 1 and rong(word[:cut]) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        lines.append(word)

    if len(lines) > TITLE_MAX_LINES:
        last = lines[TITLE_MAX_LINES - 1]
        while last and rong(last + "…") > max_width:
            last = last[:-1]
        lines = [*lines[: TITLE_MAX_LINES - 1], last.rstrip() + "…"]
    return lines or [name]


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

        y = 70
        title_font = _font(TITLE_SIZE, bold=True)
        for line in title_lines(card["name"], title_font):
            draw.text((MARGIN_X, y), line, fill=(255, 255, 255), font=title_font)
            y += TITLE_SIZE + 14

        y = max(y + 30, 330)
        if card["discount"]:
            # Nhãn giảm giá dạng khối: mắt lướt tường Facebook dừng ở màu trước chữ.
            label = f"Giảm {card['discount'].lstrip('-')}"
            badge_font = _font(44, bold=True)
            left, top, right, bottom = draw.textbbox((60, y), label, font=badge_font)
            draw.rounded_rectangle(
                (left - 16, top - 10, right + 16, bottom + 10), radius=12, fill=(220, 38, 38)
            )
            draw.text((60, y), label, fill=(255, 255, 255), font=badge_font)
            y += 90
        if card["price"]:
            draw.text((60, y), card["price"], fill=(74, 222, 128), font=_font(72, bold=True))

        draw.text((60, 540), "GameNews · giá game ở Việt Nam", fill=(148, 163, 184), font=_font(32))

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
