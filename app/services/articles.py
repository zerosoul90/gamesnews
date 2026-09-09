import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.services.admin import set_manual_aliases

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


def articles(db: Db) -> AsyncIOMotorCollection[dict[str, Any]]:
    """Collection articles chứa các bài viết."""
    return db.get_collection("articles")


async def get_pending_articles(
    db: Db, limit: int = 20, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Lấy danh sách các bài viết đang chờ duyệt."""
    limit = max(1, min(limit, 100))
    collection = articles(db)
    condition = {"status": "pending"}

    cursor = collection.find(condition).sort("created_at", -1).skip(offset).limit(limit)
    return [doc async for doc in cursor], await collection.count_documents(condition)


async def approve_article(
    db: Db, article_id: ObjectId, game_id: ObjectId, alias: str | None = None
) -> dict[str, Any]:
    """
    Duyệt một bài viết bằng tay, gán nó vào một game.
    Nếu có alias, thì tự động thêm alias này vào game đó (Vòng phản hồi sinh alias).
    """
    collection = articles(db)
    article_doc = await collection.find_one({"_id": article_id})
    if not article_doc:
        raise ValueError(f"Không tìm thấy bài viết với id {article_id}")

    # Cập nhật thông tin article
    update_data = {"status": "published", "matching_tier": "manual", "game_id": str(game_id)}

    await collection.update_one({"_id": article_id}, {"$set": update_data})

    # Nếu có alias, gọi dịch vụ admin để gán alias vào game
    if alias:
        alias = alias.strip()
        if alias:
            logger.info(f"Sinh alias tự động từ duyệt bài tay: {alias} -> game {game_id}")
            await set_manual_aliases(db, game_id, [alias])

    # Trả về bài báo đã được cập nhật
    updated_doc = await collection.find_one({"_id": article_id})
    return updated_doc or {}
