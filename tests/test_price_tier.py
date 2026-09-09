"""Phân tầng theo dõi giá — `docs/PHASE-2.md` mục 4.

Trọng tâm không phải "xếp đúng tầng" mà là hai thứ dễ hỏng âm thầm:

- game **chưa từng** kiểm giá phải luôn tới hạn (`$lt` với một mốc thời gian
  không khớp document thiếu trường — quên chỗ này thì game mới nạp về không
  bao giờ có giá, mà chẳng có lỗi nào nổi lên);
- game người dùng **đã sở hữu** không được kéo lên tầng hot.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.game import ExternalIds, Game, ReleaseDate, Titles
from app.services import price_tier
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]


async def tier_of(db: Db, **query: Any) -> str | None:
    """Tầng hiện tại của một game. Gói lại vì `find_one` trả về `| None`."""
    doc = await games(db).find_one(query)
    assert doc is not None, f"không thấy game {query}"
    tier: str | None = doc.get("price_tier")
    return tier


async def add_game(db: Db, slug: str, appid: int, **extra: Any) -> ObjectId:
    game = with_aliases(
        Game(
            slug=slug,
            titles=Titles(primary=slug.replace("-", " ").title()),
            external_ids=ExternalIds(steam_appid=appid),
            **extra,
        )
    )
    await upsert_game(db, game, key="steam_appid")
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    object_id: ObjectId = doc["_id"]
    return object_id


# --- xếp tầng --------------------------------------------------------------


async def test_dat_canh_bao_gia_thi_len_tang_hot(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    hot = await add_game(mongo_db, "elden-ring", 1245620)
    await add_game(mongo_db, "game-thuong", 999)
    await mongo_db.price_alerts.insert_one(
        {"user_id": ObjectId(), "game_id": hot, "condition": "below_price", "value": 200000}
    )

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=hot) == "hot"
    assert await tier_of(mongo_db, slug="game-thuong") == "cold"


async def test_theo_doi_game_thi_len_tang_hot(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    followed = await add_game(mongo_db, "hades-2", 1145350)
    await mongo_db.user_follows.insert_one(
        {"user_id": ObjectId(), "target_type": "game", "target_id": followed}
    )

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=followed) == "hot"


async def test_game_da_so_huu_khong_duoc_keo_len_hot(mongo_db: Db) -> None:
    """`CLAUDE.md` cấm báo giảm giá cho game người dùng đã có, nên theo dõi sát
    giá của chúng chỉ tốn quota mà không dùng vào việc gì."""
    await ensure_indexes(mongo_db)
    owned = await add_game(mongo_db, "game-da-mua", 555)
    await mongo_db.user_library.insert_one(
        {"user_id": ObjectId(), "store": "steam", "game_id": owned, "playtime_minutes": 120}
    )

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=owned) == "cold"


async def test_co_bai_viet_trong_30_ngay_thi_vao_tang_am(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game_id = await add_game(mongo_db, "game-co-tin", 777)
    recent = (dt.datetime.now(dt.UTC) - dt.timedelta(days=3)).isoformat()
    await mongo_db.articles.insert_one({"game_id": game_id, "published_at": recent})

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=game_id) == "warm"


async def test_bai_viet_cu_hon_30_ngay_thi_khong_con_am(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game_id = await add_game(mongo_db, "game-tin-cu", 778)
    old = (dt.datetime.now(dt.UTC) - dt.timedelta(days=60)).isoformat()
    await mongo_db.articles.insert_one({"game_id": game_id, "published_at": old})

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=game_id) == "cold"


async def test_game_moi_ra_mat_vao_tang_am(mongo_db: Db) -> None:
    """Game mới luôn biến động giá, kể cả khi chưa ai theo dõi."""
    await ensure_indexes(mongo_db)
    recent = (dt.datetime.now(dt.UTC) - dt.timedelta(days=10)).date().isoformat()
    game_id = await add_game(
        mongo_db,
        "game-moi",
        888,
        release_dates=[ReleaseDate(region="ww", date=recent, platform="pc")],
    )

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=game_id) == "warm"


async def test_hot_thang_am_khi_game_thoa_ca_hai(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game_id = await add_game(mongo_db, "vua-hot-vua-am", 889)
    await mongo_db.price_alerts.insert_one({"user_id": ObjectId(), "game_id": game_id})
    await mongo_db.articles.insert_one(
        {"game_id": game_id, "published_at": dt.datetime.now(dt.UTC).isoformat()}
    )

    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=game_id) == "hot"


async def test_roi_khoi_hot_thi_tu_ve_lanh(mongo_db: Db) -> None:
    """"Tầng được tính lại định kỳ, không cố định" — PHASE-2.md mục 4."""
    await ensure_indexes(mongo_db)
    game_id = await add_game(mongo_db, "tung-hot", 890)
    alert = await mongo_db.price_alerts.insert_one({"user_id": ObjectId(), "game_id": game_id})
    await price_tier.recompute_tiers(mongo_db)
    assert await tier_of(mongo_db, _id=game_id) == "hot"

    await mongo_db.price_alerts.delete_one({"_id": alert.inserted_id})
    await price_tier.recompute_tiers(mongo_db)

    assert await tier_of(mongo_db, _id=game_id) == "cold"


# --- chọn game tới hạn -----------------------------------------------------


async def test_game_chua_tung_kiem_gia_luon_toi_han(mongo_db: Db) -> None:
    """Cái bẫy chính: `$lt` với một mốc thời gian KHÔNG khớp document thiếu
    trường. Quên chỗ này thì game mới nạp về không bao giờ có giá."""
    await ensure_indexes(mongo_db)
    await add_game(mongo_db, "game-moi-toanh", 901)
    await price_tier.recompute_tiers(mongo_db)

    due = await price_tier.due_for_check(mongo_db, 10)

    assert [d["slug"] for d in due] == ["game-moi-toanh"] or len(due) == 1


async def test_chua_xep_tang_lan_nao_van_duoc_kiem(mongo_db: Db) -> None:
    """Job xếp tầng chưa chạy lượt đầu không được làm cả catalog đứng im."""
    await ensure_indexes(mongo_db)
    await add_game(mongo_db, "chua-xep-tang", 902)

    assert len(await price_tier.due_for_check(mongo_db, 10)) == 1


async def test_vua_kiem_xong_thi_chua_toi_han_lai(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game_id = await add_game(mongo_db, "vua-kiem", 903)
    await price_tier.recompute_tiers(mongo_db)
    await games(mongo_db).update_one(
        {"_id": game_id}, {"$set": {"price_checked_at": dt.datetime.now(dt.UTC)}}
    )

    assert await price_tier.due_for_check(mongo_db, 10) == []


async def test_tang_hot_toi_han_som_hon_tang_lanh(mongo_db: Db) -> None:
    """Cùng kiểm cách đây 6 tiếng: hot (chu kỳ 4h) tới hạn, lạnh (7 ngày) thì
    chưa."""
    await ensure_indexes(mongo_db)
    hot = await add_game(mongo_db, "game-hot", 904)
    cold = await add_game(mongo_db, "game-lanh", 905)
    await mongo_db.price_alerts.insert_one({"user_id": ObjectId(), "game_id": hot})
    await price_tier.recompute_tiers(mongo_db)

    six_hours_ago = dt.datetime.now(dt.UTC) - dt.timedelta(hours=6)
    await games(mongo_db).update_many(
        {"_id": {"$in": [hot, cold]}}, {"$set": {"price_checked_at": six_hours_ago}}
    )

    due = await price_tier.due_for_check(mongo_db, 10)

    assert [d["_id"] for d in due] == [hot]


async def test_cu_nhat_duoc_kiem_truoc(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    now = dt.datetime.now(dt.UTC)
    older = await add_game(mongo_db, "cu-hon", 906)
    newer = await add_game(mongo_db, "moi-hon", 907)
    await price_tier.recompute_tiers(mongo_db)
    await games(mongo_db).update_one(
        {"_id": older}, {"$set": {"price_checked_at": now - dt.timedelta(days=30)}}
    )
    await games(mongo_db).update_one(
        {"_id": newer}, {"$set": {"price_checked_at": now - dt.timedelta(days=8)}}
    )

    due = await price_tier.due_for_check(mongo_db, 10)

    assert [d["_id"] for d in due] == [older, newer]


async def test_game_khong_ban_tren_steam_thi_khong_lay(mongo_db: Db) -> None:
    """Game mobile chỉ có trên Google Play thì job giá Steam không đụng tới."""
    await ensure_indexes(mongo_db)
    mobile = with_aliases(
        Game(
            slug="chi-co-mobile",
            titles=Titles(primary="Chỉ Có Mobile"),
            external_ids=ExternalIds(google_play="com.x.y"),
        )
    )
    await upsert_game(mongo_db, mobile, key="google_play")

    assert await price_tier.due_for_check(mongo_db, 10) == []
