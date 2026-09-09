import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def rollup_time_series(db: Db) -> None:
    """
    Job dọn dẹp và rollup time-series:
    - Gom raw data (15 phút) thành data giờ.
    - Gom data giờ thành ngày (min/max/avg).
    Do giới hạn của MongoDB và framework, logic mẫu ở đây có thể dùng
    Aggregation Pipeline của MongoDB để tính toán và lưu vào bucket mới,
    hoặc dùng `$merge` / `$out` để upsert vào collection đích.
    """
    logger.info("Bắt đầu tiến trình Rollup Time-series...")
    # TODO: Thực hiện aggregation
    # Ví dụ: aggregate gộp các record theo (game_id, channel, date/hour)
    # Lấy min, max, avg, và cập nhật collection rollup_1h, rollup_1d

    # Hiện tại chạy mock
    logger.info("Hoàn thành rollup time-series (Mock).")
