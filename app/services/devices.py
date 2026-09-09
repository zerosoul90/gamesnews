"""Sổ token thiết bị cho push — `docs/PHASE-3.md`.

Trước đây không tồn tại. `send_push_notification(user_id, ...)` chỉ ghi log
nên không ai để ý rằng hệ thống **chưa bao giờ biết gửi tới đâu**: không có
chỗ nào lưu token FCM của thiết bị, và không có gì để tra khi cần gửi.

Hai điều quyết định thiết kế:

1. **Một người có nhiều thiết bị**, và cùng một thiết bị có thể đổi chủ (bán
   máy, dùng chung). Token là khoá chính, không phải user — đăng nhập tài
   khoản khác trên cùng máy phải chuyển token sang chủ mới, không nhân đôi.
2. **Token chết là chuyện thường ngày**: gỡ app, cài lại, đổi máy. FCM báo
   `UNREGISTERED`, và ta phải xoá ngay. Không xoá thì danh sách phình mãi và
   mỗi lượt gửi tốn thêm request cho những thiết bị không còn tồn tại.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

DEVICES = "user_devices"

INDEXES: list[IndexModel] = [
    # Token là khoá chính thật sự: cùng một máy chỉ có một dòng, dù đổi chủ.
    IndexModel([("token", ASCENDING)], name="token_unique", unique=True),
    IndexModel([("user_id", ASCENDING)], name="user"),
]


def devices(db: Db) -> AsyncIOMotorCollection[dict[str, Any]]:
    return db[DEVICES]


async def ensure_indexes(db: Db) -> list[str]:
    return await devices(db).create_indexes(INDEXES)


async def register(db: Db, user_id: ObjectId, token: str, *, platform: str = "android") -> bool:
    """Ghi nhận token của một thiết bị. Trả về True nếu là thiết bị mới.

    Đăng ký lại cùng token cho user khác thì **chuyển chủ**, không tạo dòng
    thứ hai: nếu không, người chủ cũ vẫn nhận thông báo trên máy đã bán đi.
    """
    token = token.strip()
    if not token:
        raise ValueError("token rỗng")

    now = dt.datetime.now(dt.UTC)
    result = await devices(db).update_one(
        {"token": token},
        {
            "$set": {"user_id": user_id, "platform": platform, "seen_at": now},
            "$setOnInsert": {"token": token, "created_at": now},
        },
        upsert=True,
    )
    return result.upserted_id is not None


async def tokens_of(db: Db, user_id: ObjectId) -> list[str]:
    cursor = devices(db).find({"user_id": user_id}, {"token": 1})
    return [doc["token"] async for doc in cursor if doc.get("token")]


async def forget(db: Db, token: str, *, reason: str = "") -> bool:
    """Xoá một token đã chết. Trả về True nếu có gì để xoá."""
    result = await devices(db).delete_one({"token": token})
    if result.deleted_count:
        logger.info("xoá token thiết bị đã chết", extra={"reason": reason})
    return bool(result.deleted_count)


async def forget_all(db: Db, user_id: ObjectId) -> int:
    """Xoá mọi thiết bị của một user — dùng khi họ yêu cầu xoá dữ liệu."""
    result = await devices(db).delete_many({"user_id": user_id})
    return int(result.deleted_count)
