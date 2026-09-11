"""Game free Epic — `app/adapters/epic/adapter.py`, `app/jobs/epic_pricing.py`.

Adapter có trong repo từ trước nhưng **không job nào gọi**, nên
`price_current.distinct("store")` chỉ trả `["steam"]`: `/free-games` luôn rỗng vì
nó đọc `price_current.is_free_promo`, và bảng so sánh giá trên trang game không
bao giờ có hơn một dòng.

Fixture là payload thật `?country=VN&locale=vi` ghi lại 2026-09-11. Nó đúng là
loại dữ liệu cần để test: 11 element, trong đó **2 game free thật** và **3 game
có `promotionalOffers` nhưng chỉ đang giảm giá thường** (Ghostrunner 2, Lost
Castle, Monument Valley). Fixture tự viết sẽ không có nhóm thứ hai, mà nhóm đó
mới là chỗ dễ gắn nhầm "miễn phí".
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import httpx
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig
from app.adapters.epic.adapter import EpicFreeGamesAdapter
from app.jobs.epic_pricing import sync_epic_free_games
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PAYLOAD = json.loads((FIXTURES / "epic_free_games.json").read_text(encoding="utf-8"))


class NoLimit:
    async def acquire(self, tokens: int = 1) -> None:
        return None


def adapter() -> EpicFreeGamesAdapter:
    return EpicFreeGamesAdapter(AdapterConfig(limiter=NoLimit()), httpx.AsyncClient())


def normalized() -> list[dict[str, Any]]:
    return adapter().normalize(PAYLOAD)


# --- adapter ----------------------------------------------------------------


def test_chi_lay_game_free_that() -> None:
    """Chốt chính của adapter.

    Bản trước đọc `discountSetting.get("discountPercentage", 0)` — mặc định 0
    nghĩa là Epic bỏ sót field một lần là cả nhóm đang giảm giá bị gắn "miễn
    phí", và `/free-games` đăng game $7.99 như thể được tặng. Điều kiện thật phải
    đọc từ giá cuối.
    """
    titles = {entry["title"] for entry in normalized()}

    assert titles == {"Luftrausers", "Astral Ascent"}
    # Ba game này có promotionalOffers trong cùng payload nhưng KHÔNG free.
    assert "Ghostrunner 2" not in titles
    assert "Monument Valley" not in titles
    assert "Lost Castle: The Old Ones Awaken" not in titles


def test_gia_goc_la_vnd_so_nguyen() -> None:
    """`country=VN` cho `originalPrice: 104000` với `decimals: 0`. Không truyền
    thì Epic trả USD theo cent (`999`, `decimals: 2`) — trộn hai thứ vào cùng cột
    `price_initial` thì so "rẻ nhất" giữa các store thành vô nghĩa."""
    by_title = {entry["title"]: entry for entry in normalized()}

    assert by_title["Luftrausers"]["currency"] == "VND"
    assert by_title["Luftrausers"]["price_initial"] == 104000
    assert by_title["Astral Ascent"]["price_initial"] == 260000


def test_slug_khong_phai_guid() -> None:
    """`productSlug` là None cho cả hai game, và `urlSlug` của Astral Ascent là
    `d72ccf025e574bb4a725e3079ea34081` — một GUID. Bản trước lưu đúng GUID đó
    vào field tên `slug`, nên URL dựng từ nó không dẫn tới đâu."""
    by_title = {entry["title"]: entry for entry in normalized()}

    assert by_title["Luftrausers"]["slug"] == "luftrausers-51e5e9"
    assert by_title["Astral Ascent"]["slug"] == "astral-ascent-b33bc2"
    assert by_title["Astral Ascent"]["slug"] != "d72ccf025e574bb4a725e3079ea34081"


def test_url_store_dung_duoc() -> None:
    by_title = {entry["title"]: entry for entry in normalized()}

    assert by_title["Luftrausers"]["url"] == "https://store.epicgames.com/p/luftrausers-51e5e9"


def test_co_han_chot_khuyen_mai() -> None:
    """`promo_ends_at` là thứ trang free dùng để nói "còn N ngày"."""
    for entry in normalized():
        assert entry["promo_ends_at"], entry["title"]
        assert entry["promo_ends_at"].startswith("2026-")


def test_payload_rong_hoac_sai_hinh_dang_khong_ne_loi() -> None:
    assert adapter().normalize({}) == []
    assert adapter().normalize({"data": None}) == []


# --- job --------------------------------------------------------------------


class FakeClients:
    def __init__(self, db: Db) -> None:
        self.db = db
        self.redis = None
        self.http = None


@pytest.fixture
def ctx_factory() -> Any:
    def make(db: Db) -> dict[str, Any]:
        return {"clients": FakeClients(db)}

    return make


async def add_game(db: Db, slug: str, primary: str) -> ObjectId:
    await ensure_indexes(db)
    game = with_aliases(
        Game(
            slug=slug,
            titles=Titles(primary=primary),
            external_ids=ExternalIds(steam_appid=abs(hash(slug)) % 10**6),
        )
    )
    await upsert_game(db, game, key="steam_appid")
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    return ObjectId(doc["_id"])


@pytest.fixture(autouse=True)
def stub_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Job không gọi mạng trong test: trả đúng payload thật đã ghi lại."""

    async def fake_fetch(self: EpicFreeGamesAdapter) -> list[dict[str, Any]]:
        return self.normalize(PAYLOAD)

    monkeypatch.setattr(EpicFreeGamesAdapter, "fetch_free_games", fake_fetch)
    monkeypatch.setattr("app.jobs.epic_pricing.RedisTokenBucket", lambda *a, **k: NoLimit())


async def test_job_ghi_gia_epic_vao_price_current(mongo_db: Db, ctx_factory: Any) -> None:
    """Chốt chính của job: trước lượt này `price_current` chỉ có store `steam`."""
    game_id = await add_game(mongo_db, "luftrausers", "LUFTRAUSERS")

    result = await sync_epic_free_games(ctx_factory(mongo_db))

    assert result["matched"] == 1
    row = await mongo_db.price_current.find_one({"game_id": game_id, "store": "epic"})
    assert row is not None
    assert row["is_free_promo"] is True
    assert row["price_final"] == 0
    assert row["price_initial"] == 104000
    assert row["currency"] == "VND"
    assert row["discount_percent"] == 100
    assert row["url"] == "https://store.epicgames.com/p/luftrausers-51e5e9"
    assert row["promo_ends_at"]


async def test_game_khong_co_trong_catalog_duoc_dem_chu_khong_im_lang(
    mongo_db: Db, ctx_factory: Any
) -> None:
    """Astral Ascent chưa có trong catalog (nó nằm trong `steam_apps` chờ
    `sync_steam_details`). Bỏ qua là đúng, nhưng bỏ qua IM LẶNG thì không ai
    biết danh sách free đang thiếu game."""
    await add_game(mongo_db, "luftrausers", "LUFTRAUSERS")

    result = await sync_epic_free_games(ctx_factory(mongo_db))

    assert result["offers"] == 2
    assert result["matched"] == 1
    assert result["unmatched"] == 1


async def test_dien_epic_slug_vao_external_ids(mongo_db: Db, ctx_factory: Any) -> None:
    """`epic_slug`/`epic_namespace` có trong model từ đầu mà chưa nguồn nào điền.
    Có chúng thì `match_by_store_link` tra được entity từ link Epic."""
    game_id = await add_game(mongo_db, "luftrausers", "LUFTRAUSERS")

    await sync_epic_free_games(ctx_factory(mongo_db))

    doc = await games(mongo_db).find_one({"_id": game_id}, {"external_ids": 1})
    assert doc is not None
    assert doc["external_ids"]["epic_slug"] == "luftrausers-51e5e9"
    assert doc["external_ids"]["epic_namespace"]


async def test_khong_de_steam_va_epic_de_len_nhau(mongo_db: Db, ctx_factory: Any) -> None:
    """Unique index là `(game_id, store, region)`. Ghi Epic không được chạm vào
    dòng Steam của cùng game — nếu không bảng so sánh giá mất một store thay vì
    có thêm một."""
    game_id = await add_game(mongo_db, "luftrausers", "LUFTRAUSERS")
    await mongo_db.price_current.insert_one(
        {
            "game_id": game_id,
            "store": "steam",
            "region": "vn",
            "currency": "VND",
            "price_initial": 104000,
            "price_final": 52000,
            "discount_percent": 50,
        }
    )

    await sync_epic_free_games(ctx_factory(mongo_db))

    rows = await mongo_db.price_current.find({"game_id": game_id}).to_list(None)
    assert {row["store"] for row in rows} == {"steam", "epic"}
    steam_row = next(row for row in rows if row["store"] == "steam")
    assert steam_row["price_final"] == 52000


async def test_chay_lai_khong_nhan_doi_dong(mongo_db: Db, ctx_factory: Any) -> None:
    """Job chạy mỗi giờ, nên `price_current` phải là upsert theo
    (game_id, store, region), không phải insert."""
    game_id = await add_game(mongo_db, "luftrausers", "LUFTRAUSERS")

    await sync_epic_free_games(ctx_factory(mongo_db))
    await sync_epic_free_games(ctx_factory(mongo_db))

    count = await mongo_db.price_current.count_documents({"game_id": game_id, "store": "epic"})
    assert count == 1
