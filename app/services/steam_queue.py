"""Hàng đợi appid Steam chờ bồi chi tiết — collection `steam_apps`.

Vì sao cần một collection riêng thay vì đổ thẳng vào `games`:

`GetAppList` trả về 184.981 mục chỉ gồm appid + tên. Ở bước đó ta **chưa biết**
mục nào thật sự là game — Steam có gắn nhãn `include_games` nhưng nhãn đó vẫn
lẫn demo, bản thử, gói sưu tập; chỉ `appdetails` mới nói được `type`. Đổ thẳng
vào `games` thì catalog có 185k entity mà phần lớn chưa biết là gì, `type` mặc
định thành "game" cho cả nhạc nền — đúng cái sai mà `PHASE-1.md` cảnh báo là
"sai ở đây thì mọi phase sau đều hỏng".

Mà bồi chi tiết thì không thể làm nhanh: appdetails giới hạn ~200 request/5
phút mỗi IP, tức khoảng 57.600 lượt/ngày, nên riêng lượt đầu đã mất nhiều ngày.
Việc đó bắt buộc phải nối lại được sau khi worker restart — nên trạng thái phải
nằm trong Mongo, không nằm trong bộ nhớ tiến trình.

`games` vì vậy chỉ chứa entity đã xác minh; `steam_apps` là sổ công việc.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel, UpdateOne

STEAM_APPS = "steam_apps"

# pending: chưa gọi appdetails lần nào.
# done:    đã thành entity trong `games`.
# skipped: appdetails nói đây không phải game (nhạc nền, phần mềm, phần cứng).
# missing: Steam trả success=false — app đã gỡ, hoặc không bán ở VN.
Status = Literal["pending", "done", "skipped", "missing"]

Db = AsyncIOMotorDatabase[dict[str, Any]]

INDEXES: list[IndexModel] = [
    # Lấy việc theo trạng thái là truy vấn nóng nhất của job bồi chi tiết.
    IndexModel([("status", ASCENDING), ("appid", ASCENDING)], name="status_appid"),
    IndexModel([("checked_at", ASCENDING)], name="checked_at"),
]


def steam_apps(db: Db) -> AsyncIOMotorCollection[dict[str, Any]]:
    return db[STEAM_APPS]


async def ensure_indexes(db: Db) -> list[str]:
    return await steam_apps(db).create_indexes(INDEXES)


async def enqueue(db: Db, apps: list[tuple[int, str]]) -> int:
    """Thêm appid mới vào hàng đợi. Trả về số mục thật sự mới.

    Chạy lại được: app đã có thì chỉ cập nhật tên và mốc nhìn thấy, **không**
    đặt lại `status`. Đặt lại thì mỗi lượt đồng bộ danh sách sẽ bắt bồi chi tiết
    toàn bộ 185k app từ đầu, mà với 57.600 lượt/ngày thì hàng đợi không bao giờ
    cạn.
    """
    if not apps:
        return 0

    now = dt.datetime.now(dt.UTC)
    operations = [
        UpdateOne(
            {"_id": appid},
            {
                "$set": {"appid": appid, "name": name, "seen_at": now},
                "$setOnInsert": {"status": "pending", "checked_at": None},
            },
            upsert=True,
        )
        for appid, name in apps
    ]
    result = await steam_apps(db).bulk_write(operations, ordered=False)
    return int(result.upserted_count)


async def take_pending(db: Db, limit: int) -> list[int]:
    """Lô appid kế tiếp cần bồi chi tiết, theo thứ tự appid tăng dần.

    Thứ tự ổn định để hai lượt chạy liên tiếp không giẫm lên nhau, và để nhìn
    log là biết đã đi tới đâu.
    """
    cursor = steam_apps(db).find({"status": "pending"}, {"appid": 1}).sort("appid", 1).limit(limit)
    return [int(doc["appid"]) async for doc in cursor]


async def mark(db: Db, appid: int, status: Status, *, reason: str | None = None) -> None:
    await steam_apps(db).update_one(
        {"_id": appid},
        {
            "$set": {
                "status": status,
                "checked_at": dt.datetime.now(dt.UTC),
                "reason": reason,
            }
        },
    )


async def counts(db: Db) -> dict[str, int]:
    """Số mục theo từng trạng thái — một dòng log là biết hàng đợi còn bao xa."""
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    return {
        str(row["_id"]): int(row["n"]) async for row in steam_apps(db).aggregate(pipeline)
    }
