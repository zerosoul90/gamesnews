"""Đường ĐỌC cho dữ liệu cá nhân hoá — thư viện, cảnh báo giá, theo dõi.

Trước module này nhóm `/api/v1/user` **chỉ có đường ghi**: `/library` có
`DELETE` và `POST /sync` nhưng không có `GET`; `/alerts` và `/follows` chỉ có
`POST`. Tức người dùng đặt được cảnh báo nhưng không xem lại được, theo dõi được
nhưng không biết mình đang theo dõi gì, và đồng bộ thư viện xong thì không có
màn nào hiển thị. Ba màn giao diện bị chặn ở đây, không phải ở tầng web.

**Mọi truy vấn trong file này đều phải kẹp `user_id`.** Không phải để lọc cho
gọn — thiếu nó thì người dùng A xoá được cảnh báo của người dùng B chỉ bằng cách
đoán một `_id`. Xoá theo `_id` trần là lỗ hổng phân quyền kinh điển, và nó im
lặng: không có lỗi nào nổi lên, chỉ có dữ liệu của người khác biến mất.

`user_library`, `price_alerts`, `user_follows` lưu `ObjectId` thật (nhờ
`mongo_document` giữ nguyên kiểu), nên join thẳng được — khác `articles` vốn lưu
`source_id`/`game_id` dạng chuỗi.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services import game_cards

Db = AsyncIOMotorDatabase[dict[str, Any]]


def _kep(limit: int, offset: int) -> tuple[int, int]:
    """Kẹp phân trang ở tầng service, không tin người gọi.

    Router đã khai `Query(le=...)`, nhưng service còn được gọi từ chỗ khác và
    một `limit` âm hay khổng lồ đi thẳng vào Mongo là chuyện không nên xảy ra.
    """
    return max(1, min(limit, 100)), max(0, offset)


async def library_of(
    db: Db, user_id: ObjectId, *, limit: int = 50, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Thư viện của một người dùng, chơi nhiều nhất trước.

    Sắp theo `playtime_minutes` giảm dần vì đó là thứ tự người ta muốn nhìn —
    thư viện 342 game xếp theo thứ tự đồng bộ thì không nói lên điều gì.

    Chỉ trả appid + playtime + mốc đồng bộ, đúng ranh giới của `CLAUDE.md`:
    **không lịch sử mua**.
    """
    limit, offset = _kep(limit, offset)
    query = {"user_id": user_id}

    cursor = (
        db.user_library.find(
            query, {"game_id": 1, "store": 1, "playtime_minutes": 1, "synced_at": 1}
        )
        .sort("playtime_minutes", -1)
        .skip(offset)
        .limit(limit)
    )
    rows = [doc async for doc in cursor]
    total = await db.user_library.count_documents(query)

    the = await game_cards.lookup(db, [r["game_id"] for r in rows if r.get("game_id")])
    items = [
        {
            "game_id": str(row["game_id"]),
            "store": row.get("store"),
            "playtime_minutes": row.get("playtime_minutes", 0),
            "synced_at": row.get("synced_at"),
            "game": the.get(str(row["game_id"])),
        }
        for row in rows
    ]
    return items, total


async def alerts_of(db: Db, user_id: ObjectId) -> list[dict[str, Any]]:
    """Cảnh báo giá của một người dùng, kèm cờ `owned`.

    **Vì sao trả cả cảnh báo cho game đã sở hữu, thay vì lọc bỏ.**
    `CLAUDE.md` cấm *gửi* cảnh báo giảm giá cho game người dùng đã có, và luật đó
    đã được thi hành đúng chỗ — `services/notification.process_notification` tra
    `user_library` trước khi gửi và **fail closed** khi không tra được.

    Giấu luôn khỏi danh sách thì lại sai kiểu khác: người dùng tự tay đặt cảnh
    báo ấy, nó biến mất không lời giải thích, và họ đặt lại. Nên trả về kèm cờ
    `owned` để giao diện làm mờ và nói rõ "bạn đã có game này" — dữ liệu không
    mất, mà kỳ vọng vẫn đúng.

    Cờ này thuần TRÌNH BÀY. Đừng để tầng nào coi nó là cơ chế chặn gửi: chặn
    thật nằm ở `notification.py`, và chỉ nên có một chỗ.
    """
    cursor = db.price_alerts.find({"user_id": user_id}).sort("_id", -1)
    rows = [doc async for doc in cursor]
    if not rows:
        return []

    game_ids = [r["game_id"] for r in rows if r.get("game_id")]
    the = await game_cards.lookup(db, game_ids)

    # Một truy vấn cho cả lô thay vì mỗi cảnh báo một lần tra thư viện.
    owned_cursor = db.user_library.find(
        {"user_id": user_id, "game_id": {"$in": game_ids}}, {"game_id": 1}
    )
    owned = {str(doc["game_id"]) async for doc in owned_cursor}

    return [
        {
            "id": str(row["_id"]),
            "game_id": str(row["game_id"]),
            "condition": row.get("condition"),
            "value": row.get("value"),
            "currency": row.get("currency", "VND"),
            "triggered_at": row.get("triggered_at"),
            "owned": str(row["game_id"]) in owned,
            "game": the.get(str(row["game_id"])),
        }
        for row in rows
    ]


async def follows_of(db: Db, user_id: ObjectId) -> list[dict[str, Any]]:
    """Những gì một người dùng đang theo dõi.

    `target_id` có thể là `ObjectId` (game) hoặc chuỗi (slug series, tên
    streamer), nên chỉ mục `target_type == "game"` mới tra được thẻ game. Mục
    khác trả `target` là `None` và giao diện hiển thị bằng `target_id` trần —
    đừng coi `None` ở đây là lỗi.
    """
    cursor = db.user_follows.find({"user_id": user_id}).sort("_id", -1)
    rows = [doc async for doc in cursor]

    game_ids = [
        r["target_id"]
        for r in rows
        if r.get("target_type") == "game" and isinstance(r.get("target_id"), ObjectId)
    ]
    the = await game_cards.lookup(db, game_ids)

    return [
        {
            "id": str(row["_id"]),
            "target_type": row.get("target_type"),
            "target_id": str(row.get("target_id")),
            "target": the.get(str(row.get("target_id"))),
        }
        for row in rows
    ]


async def delete_alert(db: Db, user_id: ObjectId, alert_id: ObjectId) -> bool:
    """Xoá một cảnh báo. Trả False khi không có gì bị xoá.

    Điều kiện `user_id` là **bắt buộc**, không phải tối ưu: thiếu nó thì ai đoán
    được `_id` cũng xoá được cảnh báo của người khác.
    """
    result = await db.price_alerts.delete_one({"_id": alert_id, "user_id": user_id})
    return result.deleted_count > 0


async def delete_follow(db: Db, user_id: ObjectId, follow_id: ObjectId) -> bool:
    """Bỏ theo dõi. Cùng luật kẹp `user_id` như `delete_alert`."""
    result = await db.user_follows.delete_one({"_id": follow_id, "user_id": user_id})
    return result.deleted_count > 0
