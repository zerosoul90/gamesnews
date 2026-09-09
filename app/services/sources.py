from __future__ import annotations

import datetime as dt
from typing import Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.source import Source

Db = AsyncIOMotorDatabase[dict[str, Any]]

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
    return result.modified_count > 0

async def update_last_crawled(db: Db, source_id: ObjectId) -> None:
    now = dt.datetime.now(dt.UTC).isoformat()
    await sources(db).update_one(
        {"_id": source_id},
        {"$set": {"last_crawled_at": now}}
    )
