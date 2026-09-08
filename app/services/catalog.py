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

from app.models.game import ExternalIds, Game, Media, ReleaseDate, SystemRequirements, Titles
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


# --- gộp hai entity trùng ------------------------------------------------
#
# Luật gộp nằm ở đây chứ không ở services/admin.py: nó là luật của entity, và
# hai đường khác nhau cùng cần nó — người bấm nút gộp trên trang admin, và job
# catalog mobile khi thấy một game có mặt trên cả hai store.


class CatalogError(RuntimeError):
    """Thao tác trên catalog không hợp lệ. Router đổi thành 4xx."""


class MergeConflictError(CatalogError):
    """Hai entity mang ID ngoài khác nhau ở cùng một nguồn.

    Đây gần như luôn có nghĩa là chúng KHÔNG phải một game: hai Steam AppID
    khác nhau là hai sản phẩm khác nhau trên cửa hàng. Gộp bừa thì mất một
    entity thật và Phase 2 lấy giá của game khác gắn vào.
    """

    def __init__(self, fields: dict[str, tuple[Any, Any]]) -> None:
        self.fields = fields
        detail = ", ".join(
            f"{field}: giữ={keep!r} bỏ={drop!r}" for field, (keep, drop) in fields.items()
        )
        super().__init__(f"xung đột external_ids ({detail}) — kiểm tra lại trước khi gộp")


def _union(primary: Iterable[str], secondary: Iterable[str]) -> list[str]:
    """Hợp hai danh sách, giữ thứ tự và không trùng. Bên giữ lại đứng trước."""
    seen: dict[str, None] = {}
    for value in (*primary, *secondary):
        if value and value not in seen:
            seen[value] = None
    return list(seen)


def _merge_external_ids(keep: ExternalIds, drop: ExternalIds) -> ExternalIds:
    """Gộp bảng ID mapping. Bên bị gộp chỉ được điền vào chỗ còn trống.

    Đây là nửa quan trọng nhất của thao tác gộp: sau khi gộp, job đồng bộ của
    nguồn bên bị gộp phải tìm thấy entity còn lại qua ID cũ của nó, nếu không
    lần chạy tới nó sẽ insert lại đúng cái entity ta vừa xoá.
    """
    merged: dict[str, Any] = {}
    conflicts: dict[str, tuple[Any, Any]] = {}

    for field in ExternalIds.model_fields:
        kept = getattr(keep, field)
        dropped = getattr(drop, field)
        if kept is not None and dropped is not None and kept != dropped:
            conflicts[field] = (kept, dropped)
        merged[field] = kept if kept is not None else dropped

    if conflicts:
        raise MergeConflictError(conflicts)
    return ExternalIds(**merged)


def _merge_release_dates(keep: list[ReleaseDate], drop: list[ReleaseDate]) -> list[ReleaseDate]:
    seen: dict[tuple[str, str | None, str | None], ReleaseDate] = {}
    for item in (*keep, *drop):
        seen.setdefault((item.region, item.platform, item.date), item)
    return list(seen.values())


def _merge_requirements(keep: SystemRequirements, drop: SystemRequirements) -> SystemRequirements:
    return SystemRequirements(
        minimum=keep.minimum or drop.minimum,
        recommended=keep.recommended or drop.recommended,
    )


def merge_content(keep: Game, drop: Game) -> Game:
    """Nội dung của entity sau khi gộp. Thuần hàm, không đụng Mongo.

    Một luật duy nhất cho mọi field, để còn đoán được kết quả: **bên giữ lại
    thắng ở chỗ nó có dữ liệu, bên bị gộp chỉ bù vào chỗ trống.** Field dạng
    danh sách thì hợp lại — mất một platform hay một studio khi gộp là mất
    dữ liệu thật, trong khi thừa một dòng thì admin xoá được.
    """
    external_ids = _merge_external_ids(keep.external_ids, drop.external_ids)
    aliases = _union(keep.aliases, drop.aliases)

    merged = keep.model_copy(
        update={
            "titles": Titles(
                primary=keep.titles.primary,
                vi=keep.titles.vi or drop.titles.vi,
                ja=keep.titles.ja or drop.titles.ja,
            ),
            "external_ids": external_ids,
            "parent_game": keep.parent_game or drop.parent_game,
            "series": keep.series or drop.series,
            "platforms": _union(keep.platforms, drop.platforms),
            "genres": _union(keep.genres, drop.genres),
            "developers": _union(keep.developers, drop.developers),
            "publishers": _union(keep.publishers, drop.publishers),
            "release_dates": _merge_release_dates(keep.release_dates, drop.release_dates),
            # Một nguồn biết đây là game dịch vụ là đủ để nó là game dịch vụ:
            # nguồn kia chỉ đơn giản không có trường đó.
            "is_live_service": keep.is_live_service or drop.is_live_service,
            "current_season": keep.current_season or drop.current_season,
            "region_locked_vn": keep.region_locked_vn or drop.region_locked_vn,
            "media": Media(
                cover=keep.media.cover or drop.media.cover,
                screenshots=_union(keep.media.screenshots, drop.media.screenshots),
                videos=_union(keep.media.videos, drop.media.videos),
            ),
            "system_requirements": _merge_requirements(
                keep.system_requirements, drop.system_requirements
            ),
        }
    )
    # Qua `with_aliases` để `aliases_normalized` được sinh lại đúng một đường
    # với mọi chỗ khác, thay vì ghép tay hai mảng normalized có sẵn.
    return with_aliases(merged, aliases)


# --- tra cứu phục vụ ghép entity ------------------------------------------


async def find_by_slug(
    db: AsyncIOMotorDatabase[dict[str, Any]], slug: str
) -> dict[str, Any] | None:
    return await games(db).find_one({"slug": slug})


async def unique_slug(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    base: str,
    *,
    suffix: str,
) -> str:
    """Slug chưa ai dùng. `slug` có index unique nên trùng là insert đổ.

    Hai game khác nhau trùng tên là chuyện thường ở store mobile ("Sudoku",
    "Ludo"). Thêm hậu tố nền tảng trước, rồi mới tới số đếm — `elden-ring`,
    `elden-ring-android`, `elden-ring-android-2`.
    """
    if await find_by_slug(db, base) is None:
        return base

    with_suffix = f"{base}-{suffix}"
    if await find_by_slug(db, with_suffix) is None:
        return with_suffix

    counter = 2
    while await find_by_slug(db, f"{with_suffix}-{counter}") is not None:
        counter += 1
    return f"{with_suffix}-{counter}"
