"""Đẩy `games` từ Mongo sang Meilisearch — `PHASE-1.md` mục 6.

Hai chế độ, đúng như tài liệu yêu cầu: reindex toàn bộ chạy lại được, và đồng
bộ delta chỉ đẩy những entity đã đổi kể từ một mốc thời gian.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.search.meili import MeiliIndex, to_search_document
from app.services.catalog import games

logger = logging.getLogger(__name__)

# Đủ lớn để không phải đi lại nhiều vòng, đủ nhỏ để một batch hỏng không kéo
# theo cả job. Meilisearch nhận payload lớn hơn nhiều, nhưng bộ nhớ tiến trình
# mới là thứ giới hạn ở đây.
BATCH_SIZE = 1000

# Chỉ lấy field mà `to_search_document` dùng tới. Kéo cả document về rồi vứt đi
# 90% là phí băng thông với vài trăm nghìn game.
_PROJECTION = {
    "slug": 1,
    "titles": 1,
    "aliases": 1,
    "aliases_normalized": 1,
    "platforms": 1,
    "genres": 1,
    "type": 1,
    "release_dates": 1,
    "media.cover": 1,
}


async def reindex(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    index: MeiliIndex,
    *,
    since: dt.datetime | None = None,
) -> int:
    """Đẩy game sang index, trả về số document đã đẩy.

    `since=None` là reindex toàn bộ. Truyền `since` thì chỉ lấy entity có
    `updated_at` mới hơn — và điều đó chỉ đúng nhờ `content_hash` ở
    `services/catalog.py`: không có nó thì lần chạy job nào cũng làm `updated_at`
    của cả catalog nhảy lên và "delta" thành "toàn bộ".
    """
    await index.ensure_index()

    query: dict[str, Any] = {} if since is None else {"updated_at": {"$gt": since}}
    cursor = games(db).find(query, _PROJECTION)

    total = 0
    batch: list[dict[str, Any]] = []
    async for doc in cursor:
        batch.append(to_search_document(doc))
        if len(batch) >= BATCH_SIZE:
            await index.add_documents(batch)
            total += len(batch)
            batch = []

    if batch:
        await index.add_documents(batch)
        total += len(batch)

    logger.info(
        "đã đẩy game sang meilisearch",
        extra={"total": total, "mode": "full" if since is None else "delta"},
    )
    return total
