"""Lưới an toàn giữa Mongo và Meilisearch.

Các job catalog vẫn tự đẩy phần mình vừa ghi ở cuối lượt chạy, để kết quả hiện
ngay. Job này tồn tại cho trường hợp dòng cuối ấy không bao giờ chạy tới — xem
`services/search_index.py` phần "mốc bền" về 2.939 game đã rơi mất theo đúng
cách đó.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.search_index import reindex_pending

logger = logging.getLogger(__name__)


async def sync_search_index(ctx: dict[str, Any]) -> int:
    index = ctx.get("meili")
    if index is None:
        return 0
    count = await reindex_pending(ctx["clients"].db, index)
    logger.info("đồng bộ index theo mốc bền", extra={"documents": count})
    return count
