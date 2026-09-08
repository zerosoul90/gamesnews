"""Đọc/ghi collection `games`. Không biết dữ liệu đến từ nguồn nào.

Đây là ranh giới mà `CLAUDE.md` yêu cầu: service làm việc với model nội bộ,
adapter lo phần nói chuyện với bên ngoài. Nhờ vậy job đồng bộ IGDB và job
scraper mobile dùng chung đúng một đường ghi.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.game import ExternalIds, Game
from app.services.normalize import build_aliases, build_aliases_normalized

GAMES = "games"

# Suy ra từ chính model, để thêm một nguồn mới không phải nhớ sửa hai chỗ.
EXTERNAL_ID_FIELDS: frozenset[str] = frozenset(ExternalIds.model_fields)

# Kết quả một lần upsert. "unchanged" là trạng thái quan trọng nhất: chạy lại
# job đồng bộ mà mọi thứ đều "unchanged" chính là bằng chứng cho checkpoint
# "chạy lại job đồng bộ không sinh entity trùng".
UpsertOutcome = Literal["inserted", "updated", "unchanged"]


def _unique_when_present(field: str, bson_type: str) -> IndexModel:
    """Unique nhưng chỉ tính những document THẬT SỰ có field đó.

    Không dùng được `sparse=True`: sparse chỉ bỏ qua document thiếu hẳn field,
    còn ở đây `external_ids.steam_appid` tồn tại với giá trị null trên phần lớn
    document (đa số game không bán trên Steam). Mongo coi nhiều null là trùng
    nhau nên index unique sẽ đổ ngay ở document thứ hai.

    `partialFilterExpression` lọc theo kiểu dữ liệu mới là công cụ đúng.
    """
    return IndexModel(
        [(f"external_ids.{field}", ASCENDING)],
        name=f"external_{field}_unique",
        unique=True,
        partialFilterExpression={f"external_ids.{field}": {"$type": bson_type}},
    )


# `PHASE-1.md` mục 2 bắt buộc bốn index đầu. Hai index cuối phục vụ job đồng bộ
# delta của mục 6.
INDEXES: list[IndexModel] = [
    IndexModel([("slug", ASCENDING)], name="slug_unique", unique=True),
    _unique_when_present("igdb", "int"),
    _unique_when_present("steam_appid", "int"),
    _unique_when_present("google_play", "string"),
    _unique_when_present("app_store", "string"),
    # Multikey: Mongo tự đánh index từng phần tử của mảng.
    IndexModel([("aliases_normalized", ASCENDING)], name="aliases_normalized"),
    IndexModel([("type", ASCENDING)], name="type"),
    IndexModel([("updated_at", DESCENDING)], name="updated_at"),
]


def games(db: AsyncIOMotorDatabase[dict[str, Any]]) -> AsyncIOMotorCollection[dict[str, Any]]:
    return db[GAMES]


async def ensure_indexes(db: AsyncIOMotorDatabase[dict[str, Any]]) -> list[str]:
    """Tạo index nếu chưa có. Chạy lại được, không lỗi."""
    return await games(db).create_indexes(INDEXES)


def with_aliases(game: Game, alternative_names: Iterable[str] = ()) -> Game:
    """Điền `aliases` và `aliases_normalized` từ tên các ngôn ngữ + tên khác.

    Mọi job nạp dữ liệu đều phải đi qua đây, đừng để job tự sinh alias. Chất
    lượng tìm kiếm phụ thuộc hoàn toàn vào bước này, và nó phải giống hệt nhau
    dù dữ liệu đến từ IGDB, từ Google Play hay từ một lần duyệt tay.
    """
    titles = {key: value for key, value in game.titles.model_dump().items() if value}
    aliases = build_aliases(titles, alternative_names)
    return game.model_copy(
        update={
            "aliases": aliases,
            "aliases_normalized": build_aliases_normalized(aliases),
        }
    )


def storage_document(game: Game, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Document đầy đủ để ghi xuống Mongo: nội dung + hai field siêu dữ liệu.

    `content_hash` và `updated_at` cố ý không nằm trong model `Game` (xem
    `models/game.py`), nên mọi đường ghi đều phải đi qua đây để gắn chúng vào.
    Bỏ sót `updated_at` một lần là job reindex delta bỏ qua entity đó vĩnh viễn.
    """
    document = game.to_mongo()
    document["content_hash"] = game.content_hash()
    document["updated_at"] = now or dt.datetime.now(dt.UTC)
    return document


async def upsert_game(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    game: Game,
    *,
    key: str,
) -> UpsertOutcome:
    """Ghi một game, định danh bằng `external_ids.<key>`.

    `key` là nguồn cầm quyền định danh cho lần ghi này: job IGDB dùng `igdb`,
    scraper Google Play dùng `google_play`. Không định danh bằng `slug` vì slug
    đổi được, còn ID của nguồn thì không.

    Chỉ ghi khi nội dung thật sự khác — xem `Game.content_hash`.

    Hai job cùng ghi một game một lúc thì index unique sẽ ném DuplicateKeyError
    ở tiến trình chậm hơn. Để nguyên cho nó nổi lên: đó là dấu hiệu hai job
    giẫm chân nhau, che đi thì lần sau không tìm ra.
    """
    if key not in EXTERNAL_ID_FIELDS:
        raise ValueError(f"{key!r} không phải field của external_ids: {sorted(EXTERNAL_ID_FIELDS)}")

    value = getattr(game.external_ids, key)
    if value is None:
        raise ValueError(f"game {game.slug!r} không có external_ids.{key}, không định danh được")

    collection = games(db)
    query = {f"external_ids.{key}": value}
    new_hash = game.content_hash()

    existing = await collection.find_one(query, {"content_hash": 1})
    if existing is not None and existing.get("content_hash") == new_hash:
        return "unchanged"

    now = dt.datetime.now(dt.UTC)
    document = storage_document(game, now=now)

    await collection.update_one(
        query,
        {"$set": document, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return "updated" if existing is not None else "inserted"


async def find_game_by_external_id(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    source: str,
    value: int | str,
) -> dict[str, Any] | None:
    """Tra ngược entity từ ID của một nguồn ngoài.

    `PHASE-1.md` mục 4: mọi phase sau đều dùng hàm này. Phase 2 có giá Steam
    kèm appid, Phase 3 có wishlist chỉ trả về appid — cả hai đều phải quay về
    được entity game.
    """
    if source not in EXTERNAL_ID_FIELDS:
        raise ValueError(
            f"{source!r} không phải nguồn đã biết: {sorted(EXTERNAL_ID_FIELDS)}"
        )
    return await games(db).find_one({f"external_ids.{source}": value})
