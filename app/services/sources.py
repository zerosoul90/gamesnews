from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.source import Source

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Nội dung tĩnh nằm ngoài mã nguồn, theo `CLAUDE.md`. Cùng chỗ với
# `jobs/mobile_seed_terms.json`.
SEED_FILE = Path(__file__).resolve().parent.parent / "jobs" / "news_sources.json"

def sources(db: Db) -> Any:
    return db["sources"]

async def create_source(db: Db, source: Source) -> dict[str, Any]:
    doc = source.to_mongo()
    result = await sources(db).insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc

async def get_sources(db: Db) -> list[dict[str, Any]]:
    cursor = sources(db).find()
    return [doc async for doc in cursor]

async def update_source_status(db: Db, source_id: str, status: str) -> bool:
    result = await sources(db).update_one(
        {"_id": ObjectId(source_id)},
        {"$set": {"status": status}}
    )
    return bool(result.modified_count > 0)

async def seed_default_sources(db: Db) -> int:
    """Mồi danh sách feed lần đầu. Trả về số nguồn đã thêm.

    **Chỉ chạy khi `sources` rỗng hoàn toàn.** Job `crawl_all_sources` đã chạy
    15 phút một lần từ lâu và lượt nào cũng trả `sources: 0, stored: 0` — mọi
    mảnh của Phase 6 đều xong, chỉ thiếu đúng cái danh sách này. Nhưng sau lượt
    mồi thì đây là dữ liệu của người vận hành: admin tắt một nguồn, hoặc xoá
    hẳn, thì lần khởi động sau không được phép dựng nó dậy.

    Từng URL trong `news_sources.json` đã được gọi thật và kiểm là parse ra bài
    trước khi đưa vào (đúng bài học "fixture của nguồn ngoài phải chép từ phản
    hồi thật"). Những feed rụng khi kiểm, ghi lại để khỏi thử lại: Polygon
    (ngắt kết nối), Kotaku (403), Mot Game (403), Vietgame.asia / Gamehub /
    Thanh Niên (404), 2Game (parse ra 0 bài).

    Một cái bẫy riêng của GameK: `mobile.rss`, `esports.rss`, `tin-tuc.rss` và
    `the-gioi-game.rss` đều trả về **y hệt** `home.rss`, nên thêm nhiều chuyên
    mục chỉ tổ nhân bản cùng một tập tin. Chỉ `pc-console.rss` khác thật, và
    cũng chỉ nó là nội dung game — mấy feed kia đầy tin showbiz.
    """
    if await sources(db).count_documents({}, limit=1):
        return 0

    try:
        raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("không đọc được danh sách nguồn mồi", extra={"path": str(SEED_FILE)})
        return 0

    docs = [Source(**entry).to_mongo() for entry in raw]
    if not docs:
        return 0

    await sources(db).insert_many(docs)
    logger.info("đã mồi nguồn tin", extra={"sources": len(docs)})
    return len(docs)

async def update_last_crawled(db: Db, source_id: ObjectId) -> None:
    now = dt.datetime.now(dt.UTC).isoformat()
    await sources(db).update_one(
        {"_id": source_id},
        {"$set": {"last_crawled_at": now}}
    )
