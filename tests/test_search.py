"""Chất lượng tìm kiếm — checkpoint khó nhất của Phase 1.

Cần Mongo và Meilisearch thật. Không mock được: thứ đang kiểm là tokenizer,
typo tolerance và ranking rules của Meilisearch, không phải code của ta.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.search.meili import FILTERABLE_ATTRIBUTES, MeiliIndex
from app.services.catalog import ensure_indexes, games, upsert_game
from app.services.search_index import reindex
from tests.conftest import load_game_fixtures

Db = AsyncIOMotorDatabase[dict[str, Any]]


@pytest_asyncio.fixture
async def seeded(mongo_db: Db, meili_index: MeiliIndex) -> MeiliIndex:
    """Nạp fixture vào Mongo rồi đẩy sang Meilisearch bằng job reindex thật."""
    await ensure_indexes(mongo_db)

    fixtures, parents = load_game_fixtures()
    for game in fixtures:
        await upsert_game(mongo_db, game, key="igdb")

    # DLC phải trỏ về game cha (PHASE-1.md mục 2).
    for child_slug, parent_slug in parents.items():
        parent = await games(mongo_db).find_one({"slug": parent_slug}, {"_id": 1})
        assert parent is not None, f"không tìm thấy game cha {parent_slug}"
        await games(mongo_db).update_one(
            {"slug": child_slug}, {"$set": {"parent_game": parent["_id"]}}
        )

    await reindex(mongo_db, meili_index)
    return meili_index


async def first_slug(index: MeiliIndex, query: str) -> str | None:
    result = await index.search(query)
    hits = result["hits"]
    return str(hits[0]["slug"]) if hits else None


# --- checkpoint: bốn cách gõ đều ra Elden Ring ----------------------------


@pytest.mark.parametrize(
    "query",
    [
        "elden ring",  # gõ đúng
        "elden",  # gõ thiếu
        "erden ring",  # gõ sai một ký tự -> typo tolerance
        "vong elden",  # tên Việt hoá, không dấu
        "Vòng Elden",  # tên Việt hoá, có dấu
        "eldenring",  # viết liền
        "エルデンリング",  # tên tiếng Nhật
    ],
)
async def test_moi_cach_go_deu_ra_elden_ring(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "elden-ring"


# --- checkpoint: game mobile phổ biến ở VN --------------------------------


@pytest.mark.parametrize("query", ["liên quân", "lien quan", "arena of valor", "AOV"])
async def test_tim_duoc_lien_quan(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "arena-of-valor"


@pytest.mark.parametrize("query", ["đế chế", "de che", "age of empires"])
async def test_tim_duoc_de_che(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "age-of-empires-ii-definitive-edition"


@pytest.mark.parametrize("query", ["liên minh huyền thoại", "lien minh huyen thoai", "LMHT"])
async def test_tim_duoc_lien_minh(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "league-of-legends"


# --- ranking: game chính trên DLC -----------------------------------------


async def test_game_chinh_xep_tren_dlc(seeded: MeiliIndex) -> None:
    """`elden` khớp cả game lẫn DLC; game phải đứng trước."""
    result = await seeded.search("elden")
    thu_tu = [hit["slug"] for hit in result["hits"]]

    assert thu_tu.index("elden-ring") < thu_tu.index("elden-ring-shadow-of-the-erdtree")


async def test_van_tim_duoc_dlc_khi_go_dung_ten(seeded: MeiliIndex) -> None:
    """type_rank đặt sau exactness, nên nó chỉ phá thế hoà chứ không đè lên độ
    khớp. Gõ đúng tên DLC thì phải ra DLC."""
    assert await first_slug(seeded, "shadow of the erdtree") == "elden-ring-shadow-of-the-erdtree"


async def test_go_dung_ten_demo_thi_ra_demo(seeded: MeiliIndex) -> None:
    assert await first_slug(seeded, "stardew valley demo") == "stardew-valley-demo"


async def test_go_ten_game_thi_ra_game_khong_ra_demo(seeded: MeiliIndex) -> None:
    assert await first_slug(seeded, "stardew valley") == "stardew-valley"


# --- số La Mã -------------------------------------------------------------


@pytest.mark.parametrize("query", ["final fantasy vii remake", "final fantasy 7 remake"])
async def test_so_la_ma_va_so_a_rap_deu_ra_dung(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "final-fantasy-vii-remake"


@pytest.mark.parametrize("query", ["dark souls iii", "dark souls 3"])
async def test_dark_souls_iii(seeded: MeiliIndex, query: str) -> None:
    assert await first_slug(seeded, query) == "dark-souls-iii"


# --- facet ----------------------------------------------------------------


async def test_facet_count_co_du_bon_nhom(seeded: MeiliIndex) -> None:
    result = await seeded.search("", facets=FILTERABLE_ATTRIBUTES, limit=0)
    assert set(result["facetDistribution"]) == set(FILTERABLE_ATTRIBUTES)


async def test_loc_theo_platform(seeded: MeiliIndex) -> None:
    result = await seeded.search("", filters=['platforms = "android"'], limit=50)
    slugs = {hit["slug"] for hit in result["hits"]}

    assert "arena-of-valor" in slugs
    assert "elden-ring" not in slugs


async def test_loc_theo_platform_va_nam(seeded: MeiliIndex) -> None:
    """Checkpoint: lọc theo platform + năm cho ra facet count đúng."""
    result = await seeded.search(
        "",
        filters=['platforms = "pc"', "release_year = 2022"],
        facets=FILTERABLE_ATTRIBUTES,
        limit=50,
    )

    assert [hit["slug"] for hit in result["hits"]] == ["elden-ring"]
    # Facet count phải phản ánh tập đã lọc, không phải toàn bộ index.
    assert result["facetDistribution"]["genres"] == {"action-rpg": 1}


async def test_facet_count_khop_voi_so_hit(seeded: MeiliIndex) -> None:
    result = await seeded.search("", facets=["platforms"], limit=0)
    so_game_pc = result["facetDistribution"]["platforms"]["pc"]

    loc = await seeded.search("", filters=['platforms = "pc"'], limit=0)
    assert loc["estimatedTotalHits"] == so_game_pc


# --- reindex --------------------------------------------------------------


async def test_reindex_chay_lai_khong_nhan_doi(
    mongo_db: Db, seeded: MeiliIndex
) -> None:
    truoc = (await seeded.search("", limit=0))["estimatedTotalHits"]
    await reindex(mongo_db, seeded)
    assert (await seeded.search("", limit=0))["estimatedTotalHits"] == truoc


async def test_reindex_delta_chi_day_entity_da_doi(
    mongo_db: Db, seeded: MeiliIndex
) -> None:
    """Đồng bộ delta dựa vào `updated_at`, mà `updated_at` chỉ nhảy khi
    `content_hash` đổi — xem services/catalog.py."""
    import datetime as dt

    moc = dt.datetime.now(dt.UTC)
    assert await reindex(mongo_db, seeded, since=moc) == 0

    fixtures, _ = load_game_fixtures()
    doi = fixtures[0].model_copy(update={"genres": ["soulslike"]})
    await upsert_game(mongo_db, doi, key="igdb")

    assert await reindex(mongo_db, seeded, since=moc) == 1
