"""Collection `games`: index, upsert idempotent, tra ngược ID.

Cần Mongo thật. Ràng buộc unique một phần và hành vi upsert là hành vi của
chính Mongo — mock lại thì test chỉ kiểm được cái mock.
"""

from __future__ import annotations

from typing import Any

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.models.game import Game, ReleaseDate, Titles
from app.services.catalog import (
    ensure_indexes,
    find_game_by_external_id,
    games,
    upsert_game,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]


def make_game(**overrides: Any) -> Game:
    base: dict[str, Any] = {
        "slug": "elden-ring",
        "titles": Titles(primary="Elden Ring"),
        "external_ids": {"igdb": 119133, "steam_appid": 1245620},
        "release_dates": [ReleaseDate(region="ww", date="2022-02-25", platform="pc")],
    }
    return Game(**(base | overrides))


# --- upsert ---------------------------------------------------------------


async def test_lan_dau_la_inserted(mongo_db: Db) -> None:
    assert await upsert_game(mongo_db, make_game(), key="igdb") == "inserted"
    assert await games(mongo_db).count_documents({}) == 1


async def test_chay_lai_y_het_thi_unchanged(mongo_db: Db) -> None:
    """Checkpoint PHASE-1: chạy lại job đồng bộ không sinh entity trùng."""
    await upsert_game(mongo_db, make_game(), key="igdb")
    assert await upsert_game(mongo_db, make_game(), key="igdb") == "unchanged"
    assert await games(mongo_db).count_documents({}) == 1


async def test_unchanged_khong_dung_toi_updated_at(mongo_db: Db) -> None:
    """Lý do tồn tại của content_hash.

    Không có nó thì mỗi lần chạy job, cả trăm nghìn document đều bị ghi đè và
    `updated_at` nhảy hết — job đồng bộ delta ở mục 6 sẽ tưởng cả catalog vừa
    thay đổi.
    """
    await upsert_game(mongo_db, make_game(), key="igdb")
    truoc = await games(mongo_db).find_one({})
    assert truoc is not None

    await upsert_game(mongo_db, make_game(), key="igdb")
    sau = await games(mongo_db).find_one({})
    assert sau is not None
    assert sau["updated_at"] == truoc["updated_at"]


async def test_noi_dung_doi_thi_updated(mongo_db: Db) -> None:
    await upsert_game(mongo_db, make_game(), key="igdb")
    outcome = await upsert_game(mongo_db, make_game(genres=["action-rpg"]), key="igdb")

    assert outcome == "updated"
    doc = await games(mongo_db).find_one({})
    assert doc is not None
    assert doc["genres"] == ["action-rpg"]
    assert await games(mongo_db).count_documents({}) == 1


async def test_update_giu_nguyen_created_at(mongo_db: Db) -> None:
    await upsert_game(mongo_db, make_game(), key="igdb")
    truoc = await games(mongo_db).find_one({})
    assert truoc is not None

    await upsert_game(mongo_db, make_game(genres=["action-rpg"]), key="igdb")
    sau = await games(mongo_db).find_one({})
    assert sau is not None
    assert sau["created_at"] == truoc["created_at"]


async def test_doi_slug_van_la_cung_mot_entity(mongo_db: Db) -> None:
    """Định danh bằng ID của nguồn, không bằng slug — slug đổi được."""
    await upsert_game(mongo_db, make_game(), key="igdb")
    await upsert_game(mongo_db, make_game(slug="elden-ring-goty"), key="igdb")

    assert await games(mongo_db).count_documents({}) == 1


async def test_key_khong_co_gia_tri_thi_bao_loi(mongo_db: Db) -> None:
    game = make_game(external_ids={"igdb": 1})
    with pytest.raises(ValueError, match="google_play"):
        await upsert_game(mongo_db, game, key="google_play")


async def test_key_la_nguon_la_thi_bao_loi(mongo_db: Db) -> None:
    with pytest.raises(ValueError, match="external_ids"):
        await upsert_game(mongo_db, make_game(), key="metacritic")


# --- index ----------------------------------------------------------------


async def test_nhieu_game_khong_co_steam_appid_van_ghi_duoc(mongo_db: Db) -> None:
    """Chốt cho `partialFilterExpression`.

    Đa số game không bán trên Steam nên `external_ids.steam_appid` là null trên
    phần lớn document. Dùng `sparse=True` thì index unique sẽ đổ ngay ở
    document thứ hai vì Mongo coi nhiều null là trùng nhau.
    """
    await ensure_indexes(mongo_db)

    for i in range(3):
        game = make_game(slug=f"game-mobile-{i}", external_ids={"igdb": 1000 + i})
        assert await upsert_game(mongo_db, game, key="igdb") == "inserted"

    assert await games(mongo_db).count_documents({}) == 3


async def test_hai_game_cung_steam_appid_bi_chan(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    await upsert_game(mongo_db, make_game(), key="igdb")

    trung = make_game(slug="ban-sao", external_ids={"igdb": 999, "steam_appid": 1245620})
    with pytest.raises(DuplicateKeyError):
        await upsert_game(mongo_db, trung, key="igdb")


async def test_hai_game_cung_slug_bi_chan(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    await upsert_game(mongo_db, make_game(), key="igdb")

    trung = make_game(external_ids={"igdb": 999})
    with pytest.raises(DuplicateKeyError):
        await upsert_game(mongo_db, trung, key="igdb")


async def test_ensure_indexes_chay_lai_duoc(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    await ensure_indexes(mongo_db)

    ten = set(await games(mongo_db).index_information())
    assert {"slug_unique", "external_igdb_unique", "aliases_normalized"} <= ten


# --- tra ngược ID ---------------------------------------------------------


async def test_tim_duoc_theo_steam_appid(mongo_db: Db) -> None:
    await upsert_game(mongo_db, make_game(), key="igdb")

    doc = await find_game_by_external_id(mongo_db, "steam_appid", 1245620)
    assert doc is not None
    assert doc["slug"] == "elden-ring"


async def test_tra_none_khi_khong_co(mongo_db: Db) -> None:
    assert await find_game_by_external_id(mongo_db, "steam_appid", 404) is None


async def test_nguon_la_thi_bao_loi(mongo_db: Db) -> None:
    with pytest.raises(ValueError, match="metacritic"):
        await find_game_by_external_id(mongo_db, "metacritic", 1)
