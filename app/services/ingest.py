"""Đường ghi chung cho mọi nguồn catalog — `docs/PHASE-1.md` mục 4, 5.

Module này **không biết** dữ liệu đến từ Google Play, App Store hay Steam: nó
nhận `Game` đã chuẩn hoá và một `key` trỏ vào `external_ids`. Đúng ranh giới
`CLAUDE.md` yêu cầu, và nhờ vậy mọi job đồng bộ dùng chung một đường ghi.

Hai chuyện phải làm cho đúng, cả hai đều dễ làm hỏng dữ liệu:

1. **Không được ghi đè dữ liệu của store kia.** Một entity đã ghép từ hai
   store, tới lượt job Play chạy mà `$set` cả document thì `external_ids.
   app_store`, platform `ios` và ảnh chụp màn hình iOS biến mất — rồi lượt sau
   job App Store lại ghi đè ngược. Hai job giẫm chân nhau vô tận và không ai
   thấy, vì mỗi lần chạy đều "thành công".
2. **Ghép entity hai store thì phải chắc.** Ghép nhầm là trộn hai game làm một,
   sai kiểu rất khó phát hiện về sau.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.game import Game
from app.services.catalog import (
    EXTERNAL_ID_FIELDS,
    MergeConflictError,
    find_game_by_external_id,
    games,
    merge_content,
    storage_document,
    unique_slug,
    upsert_game,
    with_aliases,
)
from app.services.normalize import normalize_vi

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# "linked" là kết quả đáng chú ý nhất: một game có mặt trên cả hai store và đã
# được nhập về một entity, thay vì nằm hai chỗ.
StoreOutcome = Literal["inserted", "updated", "unchanged", "linked"]

# Hậu tố slug theo nguồn, dùng khi hai game khác nhau trùng tên.
_SLUG_SUFFIX = {"google_play": "android", "app_store": "ios", "steam_appid": "pc"}


def _titles_normalized(game: Game) -> set[str]:
    return {normalize_vi(title) for title in (game.titles.primary, game.titles.vi) if title}


def _publishers_normalized(game: Game) -> set[str]:
    return {normalize_vi(name) for name in game.publishers if name}


def is_same_game(incoming: Game, candidate: Game) -> bool:
    """Luật ghép entity giữa hai store. Cố ý chặt.

    Phải khớp **cả hai**: một trong các tên (quốc tế hoặc tiếng Việt) chuẩn hoá
    trùng khít, và nhà phát hành chuẩn hoá cũng trùng khít.

    Chỉ khớp tên là không đủ — "Sudoku" của mười nhà khác nhau vẫn là mười game
    khác nhau. Còn chỉ khớp nhà phát hành thì càng không: một studio có hàng
    chục game.

    Cái giá của luật chặt: hai store thường ghi tên nhà phát hành khác nhau
    ("Garena Mobile Private" so với "GARENA ONLINE PRIVATE LIMITED"), nên phần
    lớn cặp trùng sẽ KHÔNG tự ghép mà nằm lại thành hai entity. Đó là lựa chọn
    có chủ ý: cặp bỏ sót thì nhìn thấy được và gộp tay bằng trang admin, còn
    cặp ghép nhầm thì im lặng và hỏng lâu dài.
    """
    if not _titles_normalized(incoming) & _titles_normalized(candidate):
        return False
    return bool(_publishers_normalized(incoming) & _publishers_normalized(candidate))


async def find_link_candidate(db: Db, game: Game, *, key: str) -> dict[str, Any] | None:
    """Entity của store KIA mà có vẻ cùng là một game.

    Lọc trước bằng `aliases_normalized` (index multikey lo được), rồi mới áp
    luật chặt trong Python. Bỏ qua entity đã có sẵn ID của chính store này —
    ID khác nhau ở cùng một store nghĩa là hai app khác nhau.
    """
    titles = list(_titles_normalized(game))
    if not titles:
        return None

    cursor = games(db).find({"aliases_normalized": {"$in": titles}})
    async for doc in cursor:
        candidate: dict[str, Any] = doc
        if candidate.get("external_ids", {}).get(key) is not None:
            continue
        if is_same_game(game, Game(**candidate)):
            return candidate
    return None


async def store_game(db: Db, game: Game, *, key: str) -> StoreOutcome:
    """Ghi một game từ một nguồn. Chạy lại được, không sinh entity trùng."""
    if key not in EXTERNAL_ID_FIELDS:
        raise ValueError(f"{key!r} không phải field của external_ids")

    # Mọi đường nạp dữ liệu đều phải sinh alias qua đây, không để job tự làm.
    game = with_aliases(game)

    store_id = getattr(game.external_ids, key)
    if store_id is None:
        raise ValueError(f"game {game.slug!r} không có external_ids.{key}")

    existing = await find_game_by_external_id(db, key, store_id)
    if existing is not None:
        return await _refresh(db, existing, game)

    candidate = await find_link_candidate(db, game, key=key)
    if candidate is not None:
        outcome = await _refresh(db, candidate, game)
        logger.info(
            "ghép entity hai store",
            extra={"slug": candidate["slug"], "key": key, "store_id": store_id},
        )
        return "linked" if outcome != "unchanged" else outcome

    # Entity mới: slug có index unique, mà store mobile đầy game trùng tên.
    game = game.model_copy(
        update={"slug": await unique_slug(db, game.slug, suffix=_SLUG_SUFFIX.get(key, "mobile"))}
    )
    return await upsert_game(db, game, key=key)


async def _refresh(db: Db, existing_doc: dict[str, Any], incoming: Game) -> StoreOutcome:
    """Trộn dữ liệu mới vào một entity đã có, không làm mất phần của nguồn kia.

    `merge_content` với bên **mới** làm bên giữ lại: dữ liệu vừa lấy về thắng ở
    chỗ nó có, còn entity cũ bù vào chỗ trống — nhờ vậy `external_ids` của store
    kia, platform `ios`/`android` và mọi danh sách đều còn nguyên, mà lần đồng
    bộ sau vẫn cập nhật được ảnh, tên, thể loại mới.

    Slug giữ nguyên của entity cũ: nó đã nằm trên URL và trong index tìm kiếm.
    """
    existing = Game(**existing_doc)
    try:
        merged = merge_content(incoming, existing)
    except MergeConflictError:
        # Trùng ID ở cùng một nguồn nhưng khác giá trị: đây không phải cùng một
        # game. Để nguyên entity cũ, ghi log cho người duyệt tay.
        logger.warning(
            "bỏ qua vì xung đột external_ids",
            extra={"slug": existing_doc.get("slug"), "incoming": incoming.slug},
        )
        return "unchanged"

    merged = merged.model_copy(update={"slug": existing.slug})
    document = storage_document(merged)
    if document["content_hash"] == existing_doc.get("content_hash"):
        return "unchanged"

    await games(db).update_one(
        {"_id": existing_doc["_id"]}, {"$set": document, "$unset": {"embedding_hash": ""}}
    )
    return "updated"
