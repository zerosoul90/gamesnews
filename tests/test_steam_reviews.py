"""Điểm đánh giá Steam — `app/adapters/steam/reviews.py`, `app/jobs/steam_reviews.py`.

`user_reviews` có 0 bản ghi và không có giao diện nào để viết review, nên
`community_score` luôn trả `average_score: null`. Đây là nguồn điểm thật duy nhất
đang có.

Fixture là payload thật ghi lại 2026-09-11, và nó chứa ca biên quan trọng nhất:
**appid 999999999 không tồn tại nhưng Steam vẫn trả `http 200`, `success: 1`**,
kèm `review_score: 0` / `"No user reviews"`. Không thể phân biệt với một game
thật chưa ai đánh giá — nên cả hai đều phải ra `None`, không phải `score: 0`.
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
from app.adapters.steam.reviews import SteamReviewsAdapter
from app.jobs.steam_reviews import sync_steam_reviews
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import ensure_indexes as ensure_game_indexes
from app.services.catalog import games, upsert_game, with_aliases
from app.services.reviews import REVIEWS, review_score_of, save_review_score

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REVIEW_PAYLOADS = json.loads((FIXTURES / "steam_appreviews.json").read_text(encoding="utf-8"))

ELDEN_RING = REVIEW_PAYLOADS["1245620"]
LUFTRAUSERS = REVIEW_PAYLOADS["233150"]
DARK_MESSIAH = REVIEW_PAYLOADS["2130"]
KHONG_TON_TAI = REVIEW_PAYLOADS["999999999"]


class NoLimit:
    async def acquire(self, tokens: int = 1) -> None:
        return None


def adapter() -> SteamReviewsAdapter:
    return SteamReviewsAdapter(AdapterConfig(limiter=NoLimit()), httpx.AsyncClient())


# --- adapter ----------------------------------------------------------------


def test_doc_duoc_diem_that() -> None:
    summary = adapter().normalize(ELDEN_RING)

    assert summary is not None
    assert summary["total"] == 1154113
    assert summary["positive"] == 1073777
    assert summary["negative"] == 80336
    assert summary["score_desc"] == "Very Positive"


def test_phan_tram_tich_cuc_moi_la_con_so_phan_biet_duoc() -> None:
    """`review_score` của Steam là nhóm thô 0-9: Elden Ring (1,15 triệu review)
    và Dark Messiah (84 review) đều ra 8 / "Very Positive". Chỉ % tích cực mới
    tách được hai game đó ra."""
    elden = adapter().normalize(ELDEN_RING)
    dark = adapter().normalize(DARK_MESSIAH)

    assert elden is not None and dark is not None
    assert elden["score"] == dark["score"] == 8
    assert elden["score_desc"] == dark["score_desc"]
    # Cùng nhãn nhưng khác nhau thật: 93,0% so với 84,5%.
    assert elden["positive_percent"] == 93.0
    assert dark["positive_percent"] == 84.5


def test_appid_khong_ton_tai_tra_none_chu_khong_phai_0_diem() -> None:
    """Chốt chính.

    Steam trả `http 200`, `success: 1`, `review_score: 0`,
    `review_score_desc: "No user reviews"` cho appid 999999999 — một summary hợp
    lệ hoàn hảo. Lưu nguyên nó thì trang hiện "0/10" và người đọc hiểu là game bị
    chấm 0 điểm, trong khi sự thật là ta không biết gì.
    """
    assert KHONG_TON_TAI["success"] == 1
    assert KHONG_TON_TAI["query_summary"]["review_score"] == 0

    assert adapter().normalize(KHONG_TON_TAI) is None


def test_success_false_tra_none() -> None:
    assert adapter().normalize({"success": 0}) is None
    assert adapter().normalize({}) is None


def test_payload_thieu_query_summary_tra_none() -> None:
    assert adapter().normalize({"success": 1}) is None


# --- lưu trữ ----------------------------------------------------------------


async def test_luu_ngoai_document_games(mongo_db: Db) -> None:
    """Không nhét vào `games`: `content_hash` băm cả model, mà số review tăng
    từng giờ — để trong `games` là mỗi lượt quét ghi đè cả entity và `updated_at`
    nhảy hết, đúng thứ chú thích của `content_hash` nói phải tránh."""
    game_id = ObjectId()
    summary = adapter().normalize(ELDEN_RING)
    assert summary is not None

    await save_review_score(mongo_db, game_id, "steam", summary)

    assert await mongo_db[REVIEWS].count_documents({"game_id": game_id}) == 1
    assert await mongo_db.games.count_documents({"_id": game_id}) == 0


async def test_doc_lai_khong_nhan_doi_dong(mongo_db: Db) -> None:
    game_id = ObjectId()
    summary = adapter().normalize(ELDEN_RING)
    assert summary is not None

    await save_review_score(mongo_db, game_id, "steam", summary)
    await save_review_score(mongo_db, game_id, "steam", summary)

    assert await mongo_db[REVIEWS].count_documents({"game_id": game_id, "store": "steam"}) == 1


async def test_chua_doc_lan_nao_tra_none(mongo_db: Db) -> None:
    assert await review_score_of(mongo_db, ObjectId(), "steam") is None


# --- job --------------------------------------------------------------------


class FakeClients:
    def __init__(self, db: Db) -> None:
        self.db = db
        self.redis = None
        self.http = None


async def add_game(db: Db, slug: str, primary: str, appid: int) -> ObjectId:
    await ensure_game_indexes(db)
    game = with_aliases(
        Game(slug=slug, titles=Titles(primary=primary), external_ids=ExternalIds(steam_appid=appid))
    )
    await upsert_game(db, game, key="steam_appid")
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    return ObjectId(doc["_id"])


@pytest.fixture(autouse=True)
def stub_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Job trả đúng payload thật đã ghi lại, theo appid."""
    by_appid = {
        1245620: ELDEN_RING,
        233150: LUFTRAUSERS,
        2130: DARK_MESSIAH,
        999999999: KHONG_TON_TAI,
    }

    async def fake_fetch(self: SteamReviewsAdapter, appid: int) -> dict[str, Any] | None:
        return self.normalize(by_appid.get(appid, {"success": 0}))

    monkeypatch.setattr(SteamReviewsAdapter, "fetch_summary", fake_fetch)
    monkeypatch.setattr("app.jobs.steam_reviews.RedisTokenBucket", lambda *a, **k: NoLimit())


async def test_job_ghi_diem_cho_game_co_review(mongo_db: Db) -> None:
    game_id = await add_game(mongo_db, "elden-ring", "ELDEN RING", 1245620)

    result = await sync_steam_reviews({"clients": FakeClients(mongo_db)})

    assert result["saved"] == 1
    stored = await review_score_of(mongo_db, game_id, "steam")
    assert stored is not None
    assert stored["positive_percent"] == 93.0
    assert stored["checked_at"]


async def test_job_khong_ghi_gi_cho_game_khong_co_review(mongo_db: Db) -> None:
    """Game mà Steam trả "No user reviews" thì KHÔNG có dòng nào trong
    `game_reviews` — vắng mặt là cách duy nhất nói "chưa biết"."""
    game_id = await add_game(mongo_db, "khong-co-review", "Game Không Review", 999999999)

    result = await sync_steam_reviews({"clients": FakeClients(mongo_db)})

    assert result["no_reviews"] == 1
    assert result["saved"] == 0
    assert await review_score_of(mongo_db, game_id, "steam") is None


async def test_job_uu_tien_game_chua_doc_lan_nao(
    mongo_db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Game chưa có điểm thì trang của nó đang trống; game đã có điểm từ hôm qua
    lệch vài chục review thì không ai thấy."""
    da_doc = await add_game(mongo_db, "elden-ring", "ELDEN RING", 1245620)
    summary = adapter().normalize(ELDEN_RING)
    assert summary is not None
    await save_review_score(mongo_db, da_doc, "steam", summary)
    chua_doc = await add_game(mongo_db, "luftrausers", "LUFTRAUSERS", 233150)

    # Chỉ chừa chỗ cho đúng 1 game mỗi lượt, để thứ tự ưu tiên thành thứ quyết định.
    monkeypatch.setattr("app.jobs.steam_reviews.MAX_GAMES", 1)

    await sync_steam_reviews({"clients": FakeClients(mongo_db)})

    # Chỉ đủ chỗ cho 1 game, và nó phải là game chưa đọc.
    stored = await review_score_of(mongo_db, chua_doc, "steam")
    assert stored is not None
    assert stored["positive_percent"] == 90.6


async def test_game_khong_co_steam_appid_bi_bo_qua(mongo_db: Db) -> None:
    await ensure_game_indexes(mongo_db)
    await mongo_db.games.insert_one({"slug": "chi-co-mobile", "titles": {"primary": "Mobile Only"}})

    result = await sync_steam_reviews({"clients": FakeClients(mongo_db)})

    assert result["picked"] == 0
