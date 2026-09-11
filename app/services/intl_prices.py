"""Giá quốc tế theo store — collection `price_intl`.

**Vì sao không dùng `price_current`.** Collection đó đang giữ VND ở đơn vị lớn
(990000 nghĩa là 990.000₫), còn CheapShark chỉ có USD và không có tham số đổi
quốc gia. Nhét vào cùng chỗ thì:

- `/deals` truy vấn `{"discount_percent": {"$gt": 0}}` **không lọc region**, nên
  một dòng USD sẽ lọt vào trang deal và web render `51.59` thành `52₫`.
- `price_final` là `int`, nên 51.59 USD không biểu diễn được mà không mất cent.
- Cột `price_final` sẽ mang hai thang đo tuỳ `currency`, và "rẻ nhất" giữa các
  store thành vô nghĩa — đúng cái bẫy đã tránh được ở job Epic bằng `country=VN`.

Nên giá quốc tế nằm riêng, lưu theo **cent** (tên field nói rõ thang đo), và trang
game hiển thị nó như một khối tách biệt chứ không trộn vào bảng giá VND.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

Db = AsyncIOMotorDatabase[dict[str, Any]]

PRICE_INTL = "price_intl"

INDEXES = [
    # Một dòng cho mỗi cặp (game, nguồn): đọc lại thì cập nhật, không cộng thêm.
    IndexModel([("game_id", ASCENDING), ("source", ASCENDING)], name="game_source", unique=True),
    # Job chọn game theo "lâu chưa đọc nhất".
    IndexModel([("checked_at", ASCENDING)], name="checked_at"),
]


async def ensure_indexes(db: Db) -> list[str]:
    return await db[PRICE_INTL].create_indexes(INDEXES)


async def save_intl_prices(db: Db, game_id: Any, source: str, payload: dict[str, Any]) -> None:
    """Ghi giá quốc tế của một game từ một nguồn.

    `payload` đã qua `normalize` của adapter, nên tới đây chắc chắn có ít nhất một
    deal: adapter trả None khi không store nào bán, và người gọi phải chặn None
    trước chứ không đẩy xuống đây thành một bảng giá trống.
    """
    await db[PRICE_INTL].update_one(
        {"game_id": game_id, "source": source},
        {"$set": {**payload, "checked_at": dt.datetime.now(dt.UTC).isoformat()}},
        upsert=True,
    )


async def intl_prices_of(db: Db, game_id: Any, source: str = "cheapshark") -> dict[str, Any] | None:
    """Giá quốc tế đã lưu, hoặc None khi chưa đọc được lần nào.

    None chứ không phải một dict có `deals: []`: trang phân biệt được "chưa có dữ
    liệu" với "không store nào bán", và chỉ `None` nói đúng điều thứ nhất.
    """
    doc = await db[PRICE_INTL].find_one({"game_id": game_id, "source": source}, {"_id": 0})
    if not doc:
        return None
    doc.pop("game_id", None)
    return doc
