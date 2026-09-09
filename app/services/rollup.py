"""Rollup time-series `game_metrics` — `docs/PHASE-7.md` mục 4.

`SCHEMA.md` gọi chính sách này là "bắt buộc, không phải tối ưu về sau", và có
lý do số học: một game, một kênh, đo 15 phút một lần là 35.040 điểm/năm. Nhân
với 185.000 game và 7 kênh thì ra con số không có máy nào chứa nổi. Rollup
không phải để chạy nhanh hơn — nó là điều kiện để hệ thống tồn tại quá vài
tháng.

| Độ phân giải | Giữ | Collection |
|---|---|---|
| raw 15 phút | 7 ngày | `game_metrics` (time-series) |
| gộp giờ | 90 ngày | `game_metrics_1h` |
| gộp ngày (min/max/avg/peak) | vĩnh viễn | `game_metrics_1d` |

Toàn bộ phép gộp chạy **bên trong MongoDB** bằng `$group` + `$merge`, không kéo
dữ liệu về tiến trình Python. Kéo về nghĩa là chuyển hàng triệu điểm qua mạng
mỗi giờ chỉ để cộng trung bình.

`_id` của bucket là bộ ba (game_id, channel, mốc thời gian), nên `$merge` với
`whenMatched: replace` khiến job **chạy lại được**: gộp lại cùng một giờ chỉ
ghi đè đúng bucket đó, không nhân đôi.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

RAW = "game_metrics"
HOURLY = "game_metrics_1h"
DAILY = "game_metrics_1d"

Unit = Literal["hour", "day"]

# Đúng bảng trong SCHEMA.md.
RAW_RETENTION = dt.timedelta(days=7)
HOURLY_RETENTION = dt.timedelta(days=90)

# Gộp thừa ra quá khứ một nhịp: điểm đo tới muộn (job chậm, retry) vẫn được
# đưa vào bucket của nó thay vì rơi mất.
OVERLAP = {"hour": dt.timedelta(hours=2), "day": dt.timedelta(days=1)}

INDEXES: dict[str, list[IndexModel]] = {
    HOURLY: [
        IndexModel(
            [("_id.game_id", ASCENDING), ("_id.channel", ASCENDING), ("_id.bucket", ASCENDING)],
            name="game_channel_bucket",
        ),
        IndexModel([("_id.bucket", ASCENDING)], name="bucket"),
    ],
    DAILY: [
        IndexModel(
            [("_id.game_id", ASCENDING), ("_id.channel", ASCENDING), ("_id.bucket", ASCENDING)],
            name="game_channel_bucket",
        ),
        IndexModel([("_id.bucket", ASCENDING)], name="bucket"),
    ],
}


async def ensure_metrics_collection(db: Db) -> bool:
    """Tạo `game_metrics` thành time-series collection. Trả về True nếu vừa tạo.

    `SCHEMA.md` quy định `timeField: ts`, `metaField: meta`. Không tạo đúng
    kiểu thì Mongo lặng lẽ dựng một collection thường ở lần insert đầu tiên:
    mọi thứ vẫn "chạy", chỉ là mất toàn bộ phần nén và phần đánh index theo
    thời gian mà time-series sinh ra để có — và tới lúc phát hiện thì đã có vài
    trăm triệu dòng nằm sai chỗ.
    """
    if RAW in await db.list_collection_names():
        return False
    await db.create_collection(
        RAW,
        timeseries={"timeField": "ts", "metaField": "meta", "granularity": "minutes"},
    )
    logger.info("đã tạo time-series collection", extra={"collection": RAW})
    return True


async def ensure_indexes(db: Db) -> None:
    for name, indexes in INDEXES.items():
        await db[name].create_indexes(indexes)


def _pipeline(
    source_ts_field: str, unit: Unit, since: dt.datetime, into: str
) -> list[dict[str, Any]]:
    """Pipeline gộp chung cho cả hai mức.

    Nguồn raw có `ts` + `meta.{game_id,channel}`; nguồn giờ có `_id.bucket` +
    `_id.{game_id,channel}`. Khác nhau đúng ở tên trường, nên tham số hoá là đủ.
    """
    is_raw = source_ts_field == "ts"
    ts = "$ts" if is_raw else "$_id.bucket"
    game_id = "$meta.game_id" if is_raw else "$_id.game_id"
    channel = "$meta.channel" if is_raw else "$_id.channel"
    value_min = "$value" if is_raw else "$min"
    value_max = "$value" if is_raw else "$max"
    value_avg = "$value" if is_raw else "$avg"

    return [
        {"$match": {source_ts_field: {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "game_id": game_id,
                    "channel": channel,
                    # $dateTrunc cần MongoDB 5.0+; CI chạy mongo:7.
                    "bucket": {"$dateTrunc": {"date": ts, "unit": unit}},
                },
                "min": {"$min": value_min},
                "max": {"$max": value_max},
                "avg": {"$avg": value_avg},
                "samples": {"$sum": 1 if is_raw else "$samples"},
                "last": {"$last": value_avg},
            }
        },
        # `peak` là tên mà SCHEMA.md dùng cho mức ngày; giữ cả hai để đọc chỗ
        # nào cũng ra, thay vì bắt người đọc nhớ mức nào gọi là gì.
        {"$set": {"peak": "$max", "rolled_at": "$$NOW"}},
        {"$merge": {"into": into, "on": "_id", "whenMatched": "replace"}},
    ]


async def rollup_time_series(db: Db, *, now: dt.datetime | None = None) -> dict[str, int]:
    """Gộp raw -> giờ -> ngày, rồi xoá phần đã quá hạn giữ.

    Thứ tự bắt buộc: gộp trước, xoá sau. Xoá trước thì mất luôn dữ liệu chưa
    kịp gộp, và không có đường lấy lại.
    """
    now = now or dt.datetime.now(dt.UTC)
    await ensure_metrics_collection(db)
    await ensure_indexes(db)

    # raw -> giờ
    await db[RAW].aggregate(
        _pipeline("ts", "hour", now - RAW_RETENTION - OVERLAP["hour"], HOURLY)
    ).to_list(None)

    # giờ -> ngày
    await db[HOURLY].aggregate(
        _pipeline("_id.bucket", "day", now - HOURLY_RETENTION - OVERLAP["day"], DAILY)
    ).to_list(None)

    raw_deleted = await db[RAW].delete_many({"ts": {"$lt": now - RAW_RETENTION}})
    hourly_deleted = await db[HOURLY].delete_many(
        {"_id.bucket": {"$lt": now - HOURLY_RETENTION}}
    )

    result = {
        "hourly": await db[HOURLY].count_documents({}),
        "daily": await db[DAILY].count_documents({}),
        "raw_deleted": raw_deleted.deleted_count,
        "hourly_deleted": hourly_deleted.deleted_count,
    }
    logger.info("rollup time-series xong", extra=result)
    return result
