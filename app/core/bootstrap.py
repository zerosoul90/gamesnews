"""Tạo index và collection lúc khởi động.

Vì sao cần một chỗ như thế này: mỗi service tự khai `INDEXES` và một hàm
`ensure_indexes` của riêng nó, nhưng **chỉ hai trong số đó từng được gọi** —
`steam_queue` và `price_tier`, và cả hai đều nằm trong job Steam. Index unique
của `games` (chốt "chạy lại job đồng bộ không sinh entity trùng"), index unique
token thiết bị, index unique URL bài viết, và cả time-series collection của
`game_metrics` chưa bao giờ được tạo ở môi trường thật — chúng chỉ tồn tại
trong test, vì test tự gọi tay.

Hậu quả không lộ ra ngay. Mongo vẫn nhận mọi lần ghi, chỉ là không còn gì chặn
trùng: hai job cùng lúc sinh hai entity cho một game, một thiết bị nhận cùng
một push hai lần, `game_metrics` lặng lẽ thành collection thường và mất toàn bộ
phần nén thời gian. Tới lúc phát hiện thì đã có dữ liệu bẩn phải dọn.

Chạy lại được: `create_indexes` là idempotent, còn `ensure_metrics_collection`
tự kiểm tra tồn tại trước khi tạo.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.jobs import news
from app.search.meili import MeiliIndex
from app.services import (
    catalog,
    devices,
    entity_review,
    price_tier,
    reviews,
    rollup,
    steam_queue,
)

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def ensure_storage(db: Db, index: MeiliIndex | None = None) -> dict[str, int]:
    """Tạo mọi index và collection mà hệ thống dựa vào. Trả về số index mỗi nhóm.

    Không để lỗi ở đây làm app chết: một `create_indexes` hỏng vì index cùng
    tên khác tuỳ chọn (di sản của một lần đổi lược đồ) không đáng để cả API
    không khởi động được. Ghi log lỗi rồi chạy tiếp — nhưng ghi ở mức `error`,
    vì đây là thứ phải sửa chứ không phải bỏ qua.
    """
    created: dict[str, int] = {}

    # `games` đứng đầu: mọi collection khác trỏ về nó.
    steps: list[tuple[str, Any]] = [
        ("games", catalog.ensure_indexes),
        ("games_price_tier", price_tier.ensure_indexes),
        ("steam_apps", steam_queue.ensure_indexes),
        ("user_devices", devices.ensure_indexes),
        ("entity_review_queue", entity_review.ensure_indexes),
        ("articles", news.ensure_indexes),
        # `game_reviews` có index unique `(game_id, store)`. Thiếu nó thì mỗi lượt
        # đọc điểm lại thêm một dòng cho cùng một game thay vì cập nhật, và trang
        # game lấy một dòng tuỳ ý trong đống đó.
        ("game_reviews", reviews.ensure_indexes),
    ]

    for name, ensure in steps:
        try:
            result = await ensure(db)
        except Exception:
            logger.exception("không tạo được index", extra={"group": name})
            continue
        created[name] = len(result or [])

    # Time-series phải được TẠO đúng kiểu trước lần insert đầu tiên. Insert vào
    # một collection chưa tồn tại thì Mongo dựng một collection thường, và
    # không có đường đổi kiểu sau đó ngoài việc chép lại toàn bộ dữ liệu.
    try:
        await rollup.ensure_metrics_collection(db)
        await rollup.ensure_indexes(db)
    except Exception:
        logger.exception("không dựng được time-series game_metrics")

    # Index Meilisearch cũng chưa từng được dựng ở môi trường thật: nó chỉ được
    # tạo bên trong `reindex()`, mà job đó chưa chạy lần nào trên một deploy
    # mới. Hậu quả lộ ra ngay chứ không âm thầm như phía Mongo — `/search` ném
    # 500 `index_not_found` cho mọi truy vấn, trong khi `/health` vẫn báo cả
    # bốn kho `ok` vì Meilisearch sống, chỉ là chưa có index.
    if index is not None:
        try:
            await index.ensure_index()
            created["meili_games"] = 1
        except Exception:
            logger.exception("không dựng được index Meilisearch")

    logger.info("đã dựng index", extra=created)
    return created
