import io
import logging

from fastapi import APIRouter, HTTPException, Response

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["SEO"])


@router.get("/og-image", response_class=Response)
async def generate_og_image(game: str) -> Response:
    """Tạo ảnh OpenGraph động cho trang game để share lên Facebook/Zalo."""
    if not HAS_PIL:
        # Nếu chưa cài thư viện ảnh, trả về lỗi thay vì sập server
        raise HTTPException(
            status_code=501, detail="Tính năng sinh ảnh chưa được kích hoạt trên server"
        )

    try:
        # Kích thước chuẩn OG Image cho Facebook/Zalo: 1200x630
        img = Image.new("RGB", (1200, 630), color=(15, 23, 42))  # bg-slate-900
        draw = ImageDraw.Draw(img)

        # MOCK: Tự động query Database thông qua slug "game"
        # Ở đây ta giả lập dữ liệu
        game_name = game.replace("-", " ").title()
        price = "595.000 VND"
        discount = "-30%"

        # Lưu ý: Môi trường thật cần load file .ttf (vd: Roboto-Bold.ttf)
        # Bắt buộc dùng font hỗ trợ Unicode tiếng Việt
        font = ImageFont.load_default()

        # Vẽ các thành phần của thẻ (Dùng font default nên chữ sẽ nhỏ)
        draw.text((50, 100), game_name, fill=(255, 255, 255), font=font)
        draw.text((50, 200), f"GIAM GIA: {discount}", fill=(248, 113, 113), font=font)
        draw.text((50, 250), f"GIA CHI CON: {price}", fill=(74, 222, 128), font=font)
        draw.text((50, 500), "GameNews.vn", fill=(148, 163, 184), font=font)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        return Response(
            content=buffer.getvalue(),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400"  # Cache 1 ngày để chống nghẽn server
            },
        )
    except Exception as exc:
        logger.exception("lỗi sinh ảnh chia sẻ")
        raise HTTPException(status_code=500, detail="Lỗi tạo ảnh") from exc
