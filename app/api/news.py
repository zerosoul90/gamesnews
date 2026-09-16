"""Router tin công khai.

Chỉ ĐỌC. Việc duyệt bài và gắn entity bằng tay nằm ở router `admin`, sau lớp
đăng nhập — đừng thêm đường ghi nào vào đây.
"""

from typing import Any

from fastapi import APIRouter, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.news_feed import public_feed

router = APIRouter(tags=["News"])


@router.get("/news")
async def get_news(
    request: Request,
    limit: int = Query(20, ge=1, le=50, description="Số bài mỗi trang"),
    offset: int = Query(0, ge=0, description="Bỏ qua bao nhiêu bài"),
    game_id: str | None = Query(None, description="Chỉ lấy tin của một game"),
) -> dict[str, Any]:
    """Feed tin đã có tóm tắt tiếng Việt, mới nhất trước.

    Trả kèm `total` chứ không chỉ danh sách: không có nó thì web không biết còn
    trang sau hay không, và nút "xem thêm" phải đoán bằng cách so độ dài trang
    với `limit` — sai đúng ở ca trang cuối vừa tròn.

    **Không bao giờ trả `original_content`.** Xem `services/news_feed.FIELDS`.
    """
    db: AsyncIOMotorDatabase[dict[str, Any]] = request.app.state.clients.db
    articles, total = await public_feed(db, limit=limit, offset=offset, game_id=game_id)
    return {"articles": articles, "total": total, "limit": limit, "offset": offset}
