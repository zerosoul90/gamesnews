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
import logging
import uuid
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel, UpdateOne

logger = logging.getLogger(__name__)

STEAM_APPS = "steam_apps"

# pending: chưa gọi appdetails lần nào.
# taken:   một lượt job đang xử lý. Xem `take_pending`.
# done:    đã thành entity trong `games`.
# skipped: appdetails nói đây không phải game (nhạc nền, phần mềm, phần cứng).
# missing: Steam trả success=false — app đã gỡ, hoặc không bán ở VN.
Status = Literal["pending", "taken", "done", "skipped", "missing"]

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Một lượt giữ việc tối đa bao lâu trước khi coi như đã chết và trả việc lại.
#
# Phải dài hơn hẳn một lượt chạy bình thường: lượt bồi xử lý tới 200 app và mỗi
# app còn phải chờ token của bucket dùng chung, nên vài phút là thường. Nhưng cũng
# không cần ngắn: hàng đợi có 185k mục, một lô 200 bị kẹt thêm một giờ không ảnh
# hưởng gì. Lease ngắn hơn thời gian chạy thật mới là thứ gây hại — lượt sau sẽ
# giật việc khỏi tay lượt đang làm, đúng cái mà cơ chế này sinh ra để chặn.
CLAIM_LEASE = dt.timedelta(minutes=60)

# Số vòng `take_pending` thử bù khi bị lượt khác giành mất ứng viên.
_CLAIM_ATTEMPTS = 3

INDEXES: list[IndexModel] = [
    # Lấy việc theo trạng thái là truy vấn nóng nhất của job bồi chi tiết.
    IndexModel([("status", ASCENDING), ("appid", ASCENDING)], name="status_appid"),
    IndexModel([("checked_at", ASCENDING)], name="checked_at"),
    # Đọc lại đúng lô mình vừa giành, và quét việc bị bỏ rơi.
    IndexModel([("claimed_by", ASCENDING)], name="claimed_by", sparse=True),
    IndexModel([("claimed_at", ASCENDING)], name="claimed_at", sparse=True),
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


async def reclaim_abandoned(db: Db, *, now: dt.datetime | None = None) -> int:
    """Trả lại `pending` những việc bị một lượt chết giữa đường giữ mất.

    Không có bước này thì mỗi lần worker bị kill giữa lượt là 200 app nằm
    `taken` vĩnh viễn, và hàng đợi rò rỉ dần tới lúc không còn việc nào chạy.
    """
    cutoff = (now or dt.datetime.now(dt.UTC)) - CLAIM_LEASE
    result = await steam_apps(db).update_many(
        {"status": "taken", "claimed_at": {"$lt": cutoff}},
        {"$set": {"status": "pending"}, "$unset": {"claimed_by": "", "claimed_at": ""}},
    )
    freed = int(result.modified_count)
    if freed:
        logger.warning("steam_queue: thu hồi việc bị bỏ rơi", extra={"freed": freed})
    return freed


async def take_pending(db: Db, limit: int, *, now: dt.datetime | None = None) -> list[int]:
    """GIÀNH lô appid kế tiếp, không chỉ đọc nó.

    Bản trước chỉ `find({"status": "pending"})` rồi trả về, còn trạng thái thì
    chỉ đổi SAU khi xử lý xong từng app. Nên hai lượt chạy chồng nhau đọc đúng
    **cùng một danh sách** và cùng bồi chi tiết cho cùng những app đó: gấp đôi
    request Steam cho cùng một kết quả, rồi cả hai tính ra cùng một slug cho một
    entity mới và bên chậm hơn đổ `DuplicateKeyError` giữa lượt — chính cái mà
    docstring của `upsert_game` nói là "dấu hiệu hai job giẫm chân nhau".
    Quan sát thật 2026-09-11: một lượt chạy tay trùng giờ với lượt cron phút :05.

    Giành theo ba bước, và bước 2 mới là chỗ nguyên tử: `update_many` chỉ khớp
    mục **còn** `pending`, nên hai lượt cùng nhắm một mục thì chỉ một bên đổi
    được. Bước 3 đọc lại theo `claimed_by` của chính mình, nên kết quả trả về chỉ
    gồm việc thật sự thuộc về lượt này.

    Thử lại khi giành được ít hơn yêu cầu: hai lượt chạy cùng lúc thường đọc ra
    cùng một tập ứng viên, nên bên chậm hơn mất trắng cả lô. Đo thật 2026-09-11
    với hai lượt song song: lượt thứ hai nhận về **0 app** và bỏ không cả lượt
    cron. Vòng sau thấy ứng viên khác vì lô vừa bị lấy đã thành `taken`.
    """
    moment = now or dt.datetime.now(dt.UTC)
    await reclaim_abandoned(db, now=moment)

    claim_id = uuid.uuid4().hex
    claimed: list[int] = []

    # Trần số vòng: hết việc thật thì vòng đầu đã trả rỗng và thoát ngay, còn
    # vòng lặp vô hạn ở đây sẽ quay liên tục khi nhiều worker tranh nhau.
    for _ in range(_CLAIM_ATTEMPTS):
        remaining = limit - len(claimed)
        if remaining <= 0:
            break

        cursor = (
            steam_apps(db).find({"status": "pending"}, {"_id": 1}).sort("appid", 1).limit(remaining)
        )
        candidates = [doc["_id"] async for doc in cursor]
        if not candidates:
            break

        result = await steam_apps(db).update_many(
            {"_id": {"$in": candidates}, "status": "pending"},
            {"$set": {"status": "taken", "claimed_by": claim_id, "claimed_at": moment}},
        )
        if result.modified_count == 0:
            # Bị giành sạch. Thử lại một vòng nữa với ứng viên khác, chứ đừng bỏ
            # không cả lượt.
            continue

        claimed = [
            int(doc["appid"])
            async for doc in steam_apps(db)
            .find({"claimed_by": claim_id}, {"appid": 1})
            .sort("appid", 1)
        ]

    return claimed


async def release(db: Db, appid: int) -> None:
    """Trả một app về `pending` để lượt sau thử lại.

    Dùng cho lỗi mạng: nó không phải bằng chứng app này có vấn đề. Trước khi có
    cơ chế giành việc thì chỉ cần `continue` là đủ, vì trạng thái vẫn đang
    `pending`; giờ không trả lại thì app treo ở `taken` tới hết lease.
    """
    await steam_apps(db).update_one(
        {"_id": appid, "status": "taken"},
        {"$set": {"status": "pending"}, "$unset": {"claimed_by": "", "claimed_at": ""}},
    )


async def mark(db: Db, appid: int, status: Status, *, reason: str | None = None) -> None:
    await steam_apps(db).update_one(
        {"_id": appid},
        {
            "$set": {
                "status": status,
                "checked_at": dt.datetime.now(dt.UTC),
                "reason": reason,
            },
            # Việc đã xong thì gỡ dấu giành, nếu không `reclaim_abandoned` phải
            # lọc thêm theo status và mọi mục done sẽ mang rác vĩnh viễn.
            "$unset": {"claimed_by": "", "claimed_at": ""},
        },
    )


async def counts(db: Db) -> dict[str, int]:
    """Số mục theo từng trạng thái — một dòng log là biết hàng đợi còn bao xa."""
    pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    return {str(row["_id"]): int(row["n"]) async for row in steam_apps(db).aggregate(pipeline)}
