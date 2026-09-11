"""Điểm đánh giá từ store ngoài — collection `game_reviews`.

**Không nhét vào document `games`.** `Game.content_hash()` băm toàn bộ model, và
job đồng bộ delta dùng đúng cái băm đó để biết "cái gì thật sự đổi". Số review
tăng từng giờ, nên để nó trong `games` là mỗi lượt quét lại ghi đè cả entity và
`updated_at` nhảy hết — chính điều mà chú thích của `content_hash` nói là phải
tránh. `game_hotness` đã đi đường này: dữ liệu dẫn xuất, đổi liên tục, nằm riêng.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

Db = AsyncIOMotorDatabase[dict[str, Any]]

REVIEWS = "game_reviews"

INDEXES = [
    # Một dòng cho mỗi cặp (game, store): đọc lại thì cập nhật, không cộng thêm.
    IndexModel([("game_id", ASCENDING), ("store", ASCENDING)], name="game_store", unique=True),
    # Job chọn game theo "lâu chưa đọc nhất".
    IndexModel([("checked_at", ASCENDING)], name="checked_at"),
]


async def ensure_indexes(db: Db) -> list[str]:
    return await db[REVIEWS].create_indexes(INDEXES)


async def save_review_score(db: Db, game_id: Any, store: str, summary: dict[str, Any]) -> None:
    """Ghi điểm đánh giá của một game tại một store.

    `summary` đã qua `normalize` của adapter, nên tới đây chắc chắn là điểm thật:
    adapter trả None khi `total_reviews == 0`, và người gọi phải chặn None trước
    chứ không đẩy xuống đây thành `score: 0`.
    """
    await db[REVIEWS].update_one(
        {"game_id": game_id, "store": store},
        {"$set": {**summary, "checked_at": dt.datetime.now(dt.UTC).isoformat()}},
        upsert=True,
    )


async def review_score_of(db: Db, game_id: Any, store: str = "steam") -> dict[str, Any] | None:
    """Điểm đã lưu, hoặc None khi chưa đọc được lần nào.

    None chứ không phải một dict có `score: 0`: người đọc phân biệt được "chưa có
    dữ liệu" với "bị chấm 0 điểm", và chỉ có `None` nói đúng điều thứ nhất.
    """
    doc = await db[REVIEWS].find_one({"game_id": game_id, "store": store}, {"_id": 0})
    if not doc:
        return None
    doc.pop("game_id", None)
    return doc
