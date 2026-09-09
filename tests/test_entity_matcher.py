"""Gắn entity ba tầng — `docs/PHASE-6.md` mục 3, 4.

Nguyên tắc chi phối mọi test ở đây là câu trong tài liệu: **thà bỏ sót còn hơn
gắn sai**. Vì vậy phần lớn test dưới đây kiểm rằng hệ thống **từ chối đoán**,
chứ không phải kiểm nó đoán được nhiều.
"""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.game import ExternalIds, Game, Titles
from app.services import entity_review
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases
from app.services.entity_matcher import (
    is_specific_enough,
    match_by_alias,
    match_by_store_link,
    match_entity,
    ngrams,
    store_links,
)

Db = AsyncIOMotorDatabase[dict[str, Any]]


def make_game(slug: str, primary: str, *, extra: list[str] | None = None, **ids: Any) -> Game:
    return with_aliases(
        Game(slug=slug, titles=Titles(primary=primary), external_ids=ExternalIds(**ids)),
        extra or [],
    )


async def seed(db: Db) -> dict[str, ObjectId]:
    await ensure_indexes(db)
    catalog = [
        make_game("elden-ring", "Elden Ring", steam_appid=1245620),
        make_game("elden-ring-nightreign", "Elden Ring Nightreign", steam_appid=2622380),
        make_game(
            "black-myth-wukong",
            "Black Myth: Wukong",
            extra=["Hắc Thần Thoại Ngộ Không"],
            steam_appid=2358720,
        ),
        make_game("arena-of-valor", "Arena of Valor", google_play="com.garena.game.kgvn"),
        # Hai game khác nhau, cùng một cái tên. Có thật và rất nhiều trên store.
        make_game("sudoku-a", "Sudoku", app_store="111"),
        make_game("sudoku-b", "Sudoku", app_store="222"),
        # Alias một từ ngắn — cái bẫy kinh điển.
        make_game("go", "Go", steam_appid=999001),
    ]
    ids: dict[str, ObjectId] = {}
    for game in catalog:
        key = next(k for k, v in game.external_ids.model_dump().items() if v is not None)
        await upsert_game(db, game, key=key)
        doc = await games(db).find_one({"slug": game.slug})
        assert doc is not None
        ids[game.slug] = doc["_id"]
    return ids


# --- bóc link store, không cần Mongo ---------------------------------------


def test_boc_duoc_link_cua_bon_store() -> None:
    content = """
    Xem trên <a href="https://store.steampowered.com/app/1245620/ELDEN_RING/">Steam</a>,
    hoặc https://apps.apple.com/vn/app/lien-quan/id1189041808 ,
    https://play.google.com/store/apps/details?id=com.garena.game.kgvn ,
    và https://store.epicgames.com/vi/p/alan-wake-2
    """
    assert set(store_links(content)) == {
        ("steam_appid", "1245620"),
        ("app_store", "1189041808"),
        ("google_play", "com.garena.game.kgvn"),
        ("epic_slug", "alan-wake-2"),
    }


def test_khong_co_link_thi_khong_boc_ra_gi() -> None:
    assert store_links("Bài viết không dẫn link store nào cả.") == []


# --- sinh cụm từ -----------------------------------------------------------


def test_cum_dai_duoc_sinh_truoc_cum_ngan() -> None:
    """Cụm cụ thể hơn phải được xét trước, nếu không "elden ring nightreign"
    luôn thua "elden ring"."""
    out = ngrams("elden ring nightreign ra mat", max_words=3)

    assert out[0] == "elden ring nightreign"
    assert out.index("elden ring nightreign") < out.index("elden ring")


def test_alias_mot_tu_ngan_bi_coi_la_khong_du_dac_trung() -> None:
    assert is_specific_enough("go") is False
    assert is_specific_enough("control") is False  # 7 ký tự, vẫn dưới ngưỡng
    assert is_specific_enough("elden ring") is True
    assert is_specific_enough("cyberpunk") is True  # 9 ký tự


# --- tầng 1 trên Mongo thật ------------------------------------------------


async def test_tang_1_link_steam_ra_dung_entity(mongo_db: Db) -> None:
    ids = await seed(mongo_db)
    content = "Chi tiết tại https://store.steampowered.com/app/1245620/ELDEN_RING/"

    match = await match_by_store_link(mongo_db, content)

    assert match is not None
    assert match.game_id == ids["elden-ring"]
    assert match.tier == "exact"
    assert match.confidence == 1.0
    assert match.matched_on == "steam_appid=1245620"


async def test_tang_1_link_tra_khong_ra_entity_thi_khong_gan_bua(mongo_db: Db) -> None:
    """Link tới game ta chưa nạp về là lỗ hổng catalog, không phải cái cớ để
    gắn bài vào một entity nào đó."""
    await seed(mongo_db)
    content = "https://store.steampowered.com/app/9999999/Game_La/"

    assert await match_by_store_link(mongo_db, content) is None


# --- tầng 2 ----------------------------------------------------------------


async def test_tang_2_khop_alias_trong_tieu_de_that(mongo_db: Db) -> None:
    """Tiêu đề tin thật là một câu văn, tên game chỉ là một cụm bên trong."""
    ids = await seed(mongo_db)

    match = await match_by_alias(mongo_db, "Elden Ring hé lộ ngày ra mắt bản mở rộng")

    assert match is not None
    assert match.game_id == ids["elden-ring"]
    assert match.tier == "alias"
    assert match.matched_on == "elden ring"


async def test_tang_2_uu_tien_cum_dai_hon(mongo_db: Db) -> None:
    """"Elden Ring Nightreign" phải ra bản Nightreign, không phải game gốc."""
    ids = await seed(mongo_db)

    match = await match_by_alias(mongo_db, "Elden Ring Nightreign chốt ngày phát hành")

    assert match is not None
    assert match.game_id == ids["elden-ring-nightreign"]
    assert match.matched_on == "elden ring nightreign"


async def test_tang_2_khop_ten_tieng_viet_khong_dau(mongo_db: Db) -> None:
    """`normalize_vi` lo phần bỏ dấu, nên người viết gõ có dấu hay không đều ra
    cùng một kết quả."""
    ids = await seed(mongo_db)

    for title in (
        "Hắc Thần Thoại Ngộ Không bán được 20 triệu bản",
        "hac than thoai ngo khong ban duoc 20 trieu ban",
    ):
        match = await match_by_alias(mongo_db, title)
        assert match is not None, title
        assert match.game_id == ids["black-myth-wukong"]


async def test_tang_2_hai_game_trung_ten_thi_khong_chon_cai_nao(mongo_db: Db) -> None:
    """Đúng lúc con người cần nhìn vào. Đoán bừa ở đây là gắn sai 50%."""
    await seed(mongo_db)

    assert await match_by_alias(mongo_db, "Sudoku ra bản cập nhật mới") is None


async def test_tang_2_khong_khop_alias_mot_tu_ngan(mongo_db: Db) -> None:
    """Game tên "Go" tồn tại thật. Không có chốt này thì mọi tiêu đề có chữ
    "go" đều bị gắn vào nó."""
    await seed(mongo_db)

    assert await match_by_alias(mongo_db, "Sony go ahead with new console") is None


async def test_tang_2_tieu_de_khong_nhac_game_nao_thi_bo_qua(mongo_db: Db) -> None:
    await seed(mongo_db)

    assert await match_by_alias(mongo_db, "Doanh thu ngành game Việt Nam tăng 15%") is None


# --- ghép ba tầng ----------------------------------------------------------


async def test_link_store_thang_alias_khi_ca_hai_cung_khop(mongo_db: Db) -> None:
    """Bài nhắc "Elden Ring" nhưng dẫn link Nightreign — link đáng tin hơn."""
    ids = await seed(mongo_db)

    match = await match_entity(
        mongo_db,
        "Elden Ring có bản mới",
        "Xem tại https://store.steampowered.com/app/2622380/",
    )

    assert match.game_id == ids["elden-ring-nightreign"]
    assert match.tier == "exact"


async def test_khong_tang_nao_khop_thi_tra_manual(mongo_db: Db) -> None:
    await seed(mongo_db)

    match = await match_entity(mongo_db, "Tin về một hãng phần cứng", "không có link")

    assert match.matched is False
    assert match.tier == "manual"
    assert match.confidence == 0.0


# --- hàng đợi duyệt tay + vòng phản hồi ------------------------------------


async def test_cung_mot_bai_khong_vao_hang_doi_hai_lan(mongo_db: Db) -> None:
    """Crawler chạy lại không được làm người duyệt thấy cùng một tiêu đề hàng
    chục lần."""
    await entity_review.ensure_indexes(mongo_db)
    article_id = ObjectId()

    assert await entity_review.enqueue(mongo_db, article_id=article_id, title="Tin A") is True
    assert await entity_review.enqueue(mongo_db, article_id=article_id, title="Tin A") is False
    assert len(await entity_review.pending(mongo_db)) == 1


async def test_duyet_tay_sinh_alias_va_lan_sau_tu_khop(mongo_db: Db) -> None:
    """Đây là vòng phản hồi mà PHASE-6.md đánh dấu bắt buộc. Không có nó thì
    tuần sau vẫn phải duyệt đúng cái tên ấy."""
    ids = await seed(mongo_db)
    await entity_review.ensure_indexes(mongo_db)

    title = "Vòng Elden sắp có bản mở rộng"
    # Trước khi duyệt: hệ thống chịu thua.
    assert await match_by_alias(mongo_db, title) is None

    article_id = ObjectId()
    await mongo_db.articles.insert_one({"_id": article_id, "title": title})
    await entity_review.enqueue(mongo_db, article_id=article_id, title=title)

    result = await entity_review.resolve(
        mongo_db,
        article_id=article_id,
        game_id=ids["elden-ring"],
        alias="Vòng Elden",
    )

    assert result["alias_added"] is True

    # Sau khi duyệt: tầng 2 tự khớp, không cần người nữa.
    match = await match_by_alias(mongo_db, title)
    assert match is not None
    assert match.game_id == ids["elden-ring"]
    assert match.matched_on == "vong elden"


async def test_duyet_tay_gan_game_id_vao_chinh_bai_viet(mongo_db: Db) -> None:
    ids = await seed(mongo_db)
    await entity_review.ensure_indexes(mongo_db)
    article_id = ObjectId()
    await mongo_db.articles.insert_one({"_id": article_id, "title": "Tin"})
    await entity_review.enqueue(mongo_db, article_id=article_id, title="Tin")

    await entity_review.resolve(mongo_db, article_id=article_id, game_id=ids["elden-ring"])

    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc is not None
    assert doc["game_id"] == ids["elden-ring"]
    assert doc["matching_tier"] == "manual"
    assert await entity_review.pending(mongo_db) == []


async def test_them_alias_y_het_lan_hai_thi_khong_ghi_lai(mongo_db: Db) -> None:
    """Cùng lý lẽ với `content_hash` ở catalog: `updated_at` nhảy vô cớ là job
    reindex delta phải đẩy lại một entity không đổi gì."""
    ids = await seed(mongo_db)

    assert await entity_review.add_alias(mongo_db, ids["elden-ring"], "Vòng Elden") is True
    assert await entity_review.add_alias(mongo_db, ids["elden-ring"], "Vòng Elden") is False


async def test_them_alias_cho_entity_khong_ton_tai_thi_bao_loi(mongo_db: Db) -> None:
    await seed(mongo_db)
    with pytest.raises(ValueError):
        await entity_review.add_alias(mongo_db, ObjectId(), "gì đó")


async def test_bai_khong_noi_ve_game_nao_thi_tu_choi(mongo_db: Db) -> None:
    """Tin về phần cứng, về công ty, về sự kiện — có thật và khá nhiều."""
    await entity_review.ensure_indexes(mongo_db)
    article_id = ObjectId()
    await entity_review.enqueue(mongo_db, article_id=article_id, title="NVIDIA ra mắt GPU mới")

    await entity_review.reject(mongo_db, article_id=article_id, reason="tin phần cứng")

    assert await entity_review.pending(mongo_db) == []
