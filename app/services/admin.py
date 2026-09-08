"""Nghiệp vụ admin entity — `docs/PHASE-1.md` mục 8.

Tìm entity, xem chi tiết, sửa alias, gộp hai entity trùng.

Vì sao mục này quan trọng hơn vẻ ngoài của nó: catalog sẽ được nạp từ nhiều
nguồn không biết nhau (IGDB, Google Play, App Store). Cùng một game sẽ vào
Mongo hai, ba lần dưới ba ID khác nhau, và không có thuật toán nào ghép đúng
100%. Trang admin là chỗ duy nhất sửa được những ca đó bằng tay.

Module này chỉ nói chuyện với Mongo. Việc đẩy thay đổi sang Meilisearch nằm ở
`services/search_index.py`, còn router `api/admin.py` ghép hai phần lại — sửa
entity mà quên đồng bộ index thì admin sửa xong tìm vẫn ra dữ liệu cũ.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.game import Game
from app.services.catalog import (
    EXTERNAL_ID_FIELDS,
    games,
    merge_content,
    storage_document,
    with_aliases,
)
from app.services.normalize import normalize_vi

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

MAX_SEARCH_LIMIT = 100


class AdminError(RuntimeError):
    """Thao tác admin không hợp lệ. Router đổi thành 4xx, không phải 500."""


class EntityNotFoundError(AdminError):
    """Không có entity với _id đó. Router đổi thành 404."""


# --- tìm và xem ------------------------------------------------------------


def _search_filter(query: str) -> dict[str, Any]:
    """Điều kiện tìm entity trong Mongo, không qua Meilisearch.

    Admin phải tìm được cả entity chưa kịp lên index — mà một trong những lý do
    hay phải mở trang admin lại chính là "game này tìm không ra". Dùng Meili ở
    đây thì đúng lúc cần nhất nó lại không giúp được.

    Khớp theo tiền tố trên `aliases_normalized` (index multikey lo được phần
    tiền tố), cộng thêm slug và các ID ngoài để dán URL vào ô tìm là ra.
    """
    normalized = normalize_vi(query)
    if not normalized:
        return {}

    prefix = re.escape(normalized)
    conditions: list[dict[str, Any]] = [
        {"aliases_normalized": {"$regex": f"^{prefix}"}},
        {"slug": normalized.replace(" ", "-")},
    ]

    raw = query.strip()
    for field in sorted(EXTERNAL_ID_FIELDS):
        conditions.append({f"external_ids.{field}": raw})
    if raw.isdigit():
        number = int(raw)
        conditions += [{f"external_ids.{field}": number} for field in sorted(EXTERNAL_ID_FIELDS)]

    return {"$or": conditions}


async def search_entities(
    db: Db,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Trả về (danh sách entity, tổng số khớp).

    Query rỗng thì liệt kê entity sửa gần nhất — đó là màn hình đầu tiên hữu
    ích nhất khi vừa chạy xong một job đồng bộ.
    """
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    condition = _search_filter(query)
    collection = games(db)

    cursor = collection.find(condition).sort("updated_at", -1).skip(offset).limit(limit)
    return [doc async for doc in cursor], await collection.count_documents(condition)


def to_object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise AdminError(f"{value!r} không phải _id hợp lệ")
    return ObjectId(value)


async def get_entity(db: Db, game_id: ObjectId) -> dict[str, Any]:
    doc = await games(db).find_one({"_id": game_id})
    if doc is None:
        raise EntityNotFoundError(f"không có entity {game_id}")
    return doc


def to_game(doc: dict[str, Any]) -> Game:
    """Document Mongo -> model `Game`.

    `_id`, `content_hash`, `updated_at`, `created_at`, `merged_from` bị bỏ qua:
    chúng là siêu dữ liệu của tầng lưu trữ, cố ý không nằm trong model.
    """
    return Game(**doc)


# --- sửa alias -------------------------------------------------------------


async def set_manual_aliases(db: Db, game_id: ObjectId, aliases: Iterable[str]) -> dict[str, Any]:
    """Đặt lại danh sách alias thêm tay cho một entity.

    Alias sinh từ tên (`titles`) luôn được giữ: đi qua `with_aliases` đúng như
    job đồng bộ, nên admin không thể lỡ tay xoá mất tên chính của game, và
    `aliases_normalized` không bao giờ lệch pha với `aliases`.

    Hệ quả cần biết: alias admin gõ vào là **thêm**, không phải thay. Muốn bỏ
    một alias do nguồn sinh ra thì phải sửa ở nguồn, không sửa ở đây — lần đồng
    bộ sau nguồn sẽ ghi đè.
    """
    doc = await get_entity(db, game_id)
    game = with_aliases(to_game(doc), [alias.strip() for alias in aliases if alias.strip()])

    document = storage_document(game)
    if document["content_hash"] == doc.get("content_hash"):
        return doc

    await games(db).update_one({"_id": game_id}, {"$set": document})
    logger.info("admin sửa alias", extra={"game_id": str(game_id), "aliases": len(game.aliases)})
    return await get_entity(db, game_id)


# --- gộp entity ------------------------------------------------------------


async def merge_games(db: Db, *, keep_id: ObjectId, drop_id: ObjectId) -> dict[str, Any]:
    """Gộp entity `drop_id` vào `keep_id`, trả về entity còn lại.

    Ba việc phải làm cùng nhau, thiếu một là hỏng dữ liệu:

    1. Nội dung + `external_ids` + `aliases` dồn về bên giữ lại.
    2. DLC đang trỏ `parent_game` vào bên bị gộp phải được trỏ lại — không thì
       chúng thành mồ côi, trỏ vào một _id không còn tồn tại.
    3. Xoá bên bị gộp.

    Thứ tự bắt buộc là **xoá trước, ghi sau**: index unique một phần trên
    `external_ids` sẽ chặn ngay nếu ta gán ID của bên bị gộp cho bên giữ lại
    trong khi document cũ còn đó. Mongo standalone không có transaction, nên
    nếu bước ghi hỏng thì hoàn tác bằng cách insert lại document vừa xoá.
    """
    if keep_id == drop_id:
        raise AdminError("không gộp một entity vào chính nó")

    keep_doc = await get_entity(db, keep_id)
    drop_doc = await get_entity(db, drop_id)

    # Tính nội dung mới TRƯỚC khi xoá: xung đột external_ids phải nổ ra lúc
    # chưa có gì bị mất.
    merged = merge_content(to_game(keep_doc), to_game(drop_doc))

    collection = games(db)
    await collection.delete_one({"_id": drop_id})
    try:
        now = dt.datetime.now(dt.UTC)
        document = storage_document(merged, now=now)
        # Dấu vết để lần ngược: entity này từng là hai entity, và ID cũ kia có
        # thể còn nằm trong log hoặc trong dữ liệu của một phase khác.
        document["merged_from"] = [
            *(keep_doc.get("merged_from") or []),
            *(drop_doc.get("merged_from") or []),
            {"_id": drop_id, "slug": drop_doc.get("slug"), "at": now},
        ]
        await collection.update_one({"_id": keep_id}, {"$set": document})
    except Exception:
        await collection.insert_one(drop_doc)
        raise

    orphans = await collection.update_many(
        {"parent_game": drop_id}, {"$set": {"parent_game": keep_id}}
    )
    if keep_doc.get("parent_game") == drop_id:
        # Gộp game cha vào chính DLC của nó thì entity còn lại không thể là con
        # của chính mình.
        await collection.update_one({"_id": keep_id}, {"$set": {"parent_game": None}})

    logger.info(
        "admin gộp entity",
        extra={
            "keep": str(keep_id),
            "drop": str(drop_id),
            "reparented": orphans.modified_count,
        },
    )
    return await get_entity(db, keep_id)
