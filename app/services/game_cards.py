"""Thẻ game rút gọn — tên, slug, ảnh bìa — cho mọi danh sách trỏ tới game.

Ba nơi đã cần đúng thứ này: `/deals` (`api/prices._attach_games`), feed tin
(`news_feed._gan_game`), và nay là nhóm endpoint cá nhân hoá. Hai bản trước ra
đời độc lập; đây là bản dùng chung cho mã mới.

**Chưa gộp hai bản cũ vào đây** có chủ ý: chúng đang phục vụ endpoint chạy thật,
và đổi chúng trong cùng lượt thêm tính năng là trộn hai loại rủi ro vào một
diff. Ghi vào sổ nợ, dọn riêng.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def lookup(db: Db, ids: list[ObjectId]) -> dict[str, dict[str, Any]]:
    """Bảng `str(game_id)` -> thẻ game. MỘT truy vấn cho cả lô.

    Khoá là **chuỗi** chứ không phải `ObjectId`: người gọi luôn phải `str()` khi
    dựng JSON trả về, nên tra bằng chuỗi khiến chỗ gọi khỏi đổi kiểu hai lần.

    Game đã bị xoá khỏi catalog thì vắng mặt trong bảng — người gọi phải phân
    biệt "không có thẻ" với "thẻ rỗng", vì hai thứ đó hiển thị khác nhau.
    """
    if not ids:
        return {}

    out: dict[str, dict[str, Any]] = {}
    cursor = db.games.find({"_id": {"$in": ids}}, {"titles": 1, "slug": 1, "media.cover": 1})
    async for doc in cursor:
        titles = doc.get("titles") or {}
        out[str(doc["_id"])] = {
            # Tên tiếng Việt trước — cùng luật với `/deals` và feed tin.
            "title": titles.get("vi") or titles.get("primary"),
            "slug": doc.get("slug"),
            "cover_image_url": (doc.get("media") or {}).get("cover"),
        }
    return out
