from typing import Any

from fastapi import APIRouter

from app.core.deps import MongoDep
from app.models.source import Source
from app.services import sources as service

router = APIRouter(tags=["sources"], prefix="/admin/api/sources")

@router.post("")
async def create_source(db: MongoDep, source: Source) -> dict[str, Any]:
    doc = await service.create_source(db, source)
    doc["_id"] = str(doc["_id"])
    return doc

@router.get("")
async def get_sources(db: MongoDep) -> list[dict[str, Any]]:
    docs = await service.get_sources(db)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs

@router.patch("/{source_id}/status")
async def update_status(db: MongoDep, source_id: str, status: str) -> dict[str, Any]:
    success = await service.update_source_status(db, source_id, status)
    return {"success": success}
