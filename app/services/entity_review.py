"""Hàng đợi duyệt tay + vòng phản hồi alias — `docs/PHASE-6.md` mục 3 và 4.

Tài liệu viết về vòng phản hồi này:

> Mỗi lần duyệt tay trong `entity_review_queue` phải **tự động sinh alias mới**
> cho `games.aliases` và `aliases_normalized`.
> Không có vòng này thì sẽ phải duyệt tay mãi mãi và hệ thống không bao giờ khá
> lên. Đây là yêu cầu bắt buộc, không phải tối ưu.

Đó chính là toàn bộ lý do file này tồn tại. Hàng đợi mà không có vòng phản hồi
thì mỗi tuần lại duyệt lại đúng những cái tên ấy: "Hắc Thần Thoại Ngộ Không"
hôm nay, và tuần sau vẫn thế, vì không có gì học được.

**Alias do người duyệt chỉ định, không tự cắt từ tiêu đề.** Tiêu đề tin là câu
văn ("Elden Ring Nightreign hé lộ ngày ra mắt chính thức"); nhét nguyên nó vào
`aliases` thì lần sau mọi bài có chữ "hé lộ ngày ra mắt" đều khớp vào game đó.
Phần tự động nằm ở chỗ khác: hệ thống nhận cụm người duyệt chọn rồi tự chuẩn
hoá, tự nối vào cả `aliases` lẫn `aliases_normalized`, tự cập nhật
`content_hash` để lần reindex sau đẩy đúng entity đó sang Meilisearch.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from app.models.game import Game
from app.services.catalog import games, storage_document, with_aliases

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

ENTITY_REVIEW_QUEUE = "entity_review_queue"

ReviewStatus = Literal["pending", "resolved", "rejected"]

INDEXES: list[IndexModel] = [
    # Lấy việc chờ duyệt là truy vấn nóng nhất của màn hình duyệt tay.
    IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created"),
    # Một bài chỉ vào hàng đợi một lần, dù crawler chạy lại bao nhiêu lượt.
    IndexModel([("article_id", ASCENDING)], name="article_unique", unique=True),
]


def queue(db: Db) -> AsyncIOMotorCollection[dict[str, Any]]:
    return db[ENTITY_REVIEW_QUEUE]


async def ensure_indexes(db: Db) -> list[str]:
    return await queue(db).create_indexes(INDEXES)


async def enqueue(
    db: Db,
    *,
    article_id: ObjectId,
    title: str,
    url: str | None = None,
) -> bool:
    """Đưa một bài vào hàng đợi. Trả về False nếu nó đã ở đó rồi.

    Chạy lại crawler không được sinh thêm dòng chờ duyệt cho cùng một bài —
    người duyệt sẽ thấy cùng một tiêu đề lặp lại hàng chục lần và bỏ cuộc.
    """
    now = dt.datetime.now(dt.UTC)
    result = await queue(db).update_one(
        {"article_id": article_id},
        {
            "$set": {"title": title, "url": url},
            "$setOnInsert": {
                "article_id": article_id,
                "status": "pending",
                "created_at": now,
                "resolved_at": None,
                "game_id": None,
            },
        },
        upsert=True,
    )
    return result.upserted_id is not None


async def pending(db: Db, limit: int = 50) -> list[dict[str, Any]]:
    """Bài đang chờ duyệt, cũ trước — tin cũ mất giá trị nhanh nhất."""
    cursor = queue(db).find({"status": "pending"}).sort("created_at", ASCENDING).limit(limit)
    return [doc async for doc in cursor]


async def add_alias(db: Db, game_id: ObjectId, alias: str) -> bool:
    """Nối một alias vào entity. Trả về False nếu entity đã có alias đó.

    Đi qua `with_aliases` đúng như mọi job đồng bộ, nên `aliases_normalized`
    không bao giờ lệch pha với `aliases`, và `content_hash` được tính lại để
    lần reindex delta kế tiếp đẩy đúng entity này sang Meilisearch.
    """
    alias = " ".join(alias.split())
    if not alias:
        return False

    doc = await games(db).find_one({"_id": game_id})
    if doc is None:
        raise ValueError(f"không có entity {game_id}")

    game = with_aliases(Game(**doc), [*(doc.get("aliases") or []), alias])
    document = storage_document(game)
    if document["content_hash"] == doc.get("content_hash"):
        return False

    await games(db).update_one(
        {"_id": game_id}, {"$set": document, "$unset": {"embedding_hash": ""}}
    )
    logger.info("vòng phản hồi: thêm alias", extra={"game_id": str(game_id), "alias": alias})
    return True


async def resolve(
    db: Db,
    *,
    article_id: ObjectId,
    game_id: ObjectId,
    alias: str | None = None,
) -> dict[str, Any]:
    """Người duyệt chỉ định entity đúng cho một bài.

    Ba việc phải xảy ra cùng nhau, thiếu việc thứ ba là hàng đợi không bao giờ
    ngắn lại:

    1. đánh dấu dòng chờ duyệt là đã xử lý;
    2. gắn `game_id` vào chính bài viết;
    3. **nếu người duyệt có chỉ ra cụm từ**, nối nó vào alias của entity để lần
       sau tầng 2 tự khớp.
    """
    now = dt.datetime.now(dt.UTC)

    await queue(db).update_one(
        {"article_id": article_id},
        {"$set": {"status": "resolved", "game_id": game_id, "resolved_at": now}},
    )
    await db.articles.update_one(
        {"_id": article_id},
        {"$set": {"game_id": game_id, "matching_tier": "manual", "matched_at": now}},
    )

    alias_added = await add_alias(db, game_id, alias) if alias else False
    if alias is None:
        # Không chặn, nhưng phải thấy được: mỗi lần duyệt mà không sinh alias
        # là một lần hệ thống không học được gì.
        logger.warning(
            "duyệt tay nhưng không kèm alias, vòng phản hồi không chạy",
            extra={"article_id": str(article_id), "game_id": str(game_id)},
        )

    return {"resolved": True, "alias_added": alias_added}


async def reject(db: Db, *, article_id: ObjectId, reason: str | None = None) -> None:
    """Bài không nói về game nào cả. Có thật và khá nhiều — tin về phần cứng,
    về công ty, về sự kiện."""
    await queue(db).update_one(
        {"article_id": article_id},
        {
            "$set": {
                "status": "rejected",
                "reason": reason,
                "resolved_at": dt.datetime.now(dt.UTC),
            }
        },
    )
