"""Catalog mobile — `docs/PHASE-1.md` mục 5.

Không test nào ở đây được gọi ra Internet: App Store đi qua `httpx.MockTransport`
với payload thật đã ghi lại, Google Play thì hai hàm của thư viện được tiêm vào
adapter. Nguồn ngoài đổi hình dạng là chuyện sẽ xảy ra, nhưng phải phát hiện
bằng giám sát, không phải bằng một suite test đỏ ngẫu nhiên.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.app_store.adapter import AppStoreAdapter, with_international_name
from app.adapters.app_store.adapter import to_game as app_store_to_game
from app.adapters.base import AdapterConfig, PermanentError, RetryPolicy
from app.adapters.google_play.adapter import GooglePlayAdapter
from app.adapters.google_play.adapter import to_game as play_to_game
from app.jobs.mobile_catalog import _titles_to_probe, seed_terms
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import ensure_indexes, games, unique_slug, upsert_game
from app.services.ingest import find_link_candidate, is_same_game, store_game

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CHART = json.loads((FIXTURES / "app_store_chart.json").read_text(encoding="utf-8"))
LOOKUP = json.loads((FIXTURES / "app_store_lookup.json").read_text(encoding="utf-8"))
PLAY = json.loads((FIXTURES / "google_play_apps.json").read_text(encoding="utf-8"))
PLAY_APPS = PLAY["apps"]
PLAY_SEARCH = PLAY["search"]

AOV_LOOKUP = LOOKUP["results"][0]


class CountingLimiter:
    def __init__(self) -> None:
        self.acquired = 0

    async def acquire(self, tokens: int = 1) -> None:
        self.acquired += tokens


def config() -> AdapterConfig:
    return AdapterConfig(
        limiter=CountingLimiter(),
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0, jitter=0.0),
    )


# --- ánh xạ App Store ------------------------------------------------------


def test_app_store_map_du_anh_va_id() -> None:
    game = app_store_to_game(AOV_LOOKUP)

    assert game.external_ids.app_store == "1189041808"
    assert game.titles.primary == "Liên Quân Mobile"
    assert len(game.media.screenshots) == 2


def test_app_store_bo_nhan_the_loai_o_du() -> None:
    """Mọi game đều nằm trong "Games"; giữ nhãn đó thì facet thể loại vô dụng."""
    game = app_store_to_game(AOV_LOOKUP)

    assert "games" not in game.genres
    assert "entertainment" not in game.genres
    assert game.genres == ["action", "role-playing"]


def test_app_store_map_dung_cac_truong_con_lai() -> None:
    game = app_store_to_game(AOV_LOOKUP)

    assert game.platforms == ["ios"]
    # Store chỉ lộ tên tài khoản bán, tức nhà phát hành — không phải studio.
    assert game.publishers == ["GARENA ONLINE PRIVATE LIMITED"]
    assert game.developers == []
    assert [(rd.region, rd.date, rd.platform) for rd in game.release_dates] == [
        ("vn", "2016-11-18", "ios")
    ]
    assert game.media.cover == "https://is1.example.test/aov/512x512.jpg"


def test_app_store_thieu_id_la_loi_vinh_vien() -> None:
    """Gọi lại vẫn thiếu, nên retry chỉ tốn quota."""
    with pytest.raises(PermanentError):
        app_store_to_game({"trackName": "Không có id"})


def test_ten_quoc_te_thanh_ten_chinh_ten_viet_xuong_titles_vi() -> None:
    """Không có bước này thì mọi game mobile vào catalog dưới tên tiếng Việt và
    không còn đường ghép với Google Play hay IGDB."""
    game = with_international_name(app_store_to_game(AOV_LOOKUP), "Arena of Valor")

    assert game.titles.primary == "Arena of Valor"
    assert game.titles.vi == "Liên Quân Mobile"
    assert game.slug == "arena-of-valor"


def test_khong_ban_o_my_thi_giu_nguyen_ten_viet() -> None:
    game = app_store_to_game(AOV_LOOKUP)
    assert with_international_name(game, None).titles.primary == "Liên Quân Mobile"


# --- adapter App Store qua HTTP giả ----------------------------------------


def app_store_adapter(handler: Any) -> AppStoreAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AppStoreAdapter(config(), http)


async def test_bang_xep_hang_lay_id_tu_payload_rss_doi_cu() -> None:
    """Endpoint RSS đời cũ là chỗ DUY NHẤT lọc được bảng xếp hạng theo thể loại
    game; payload của nó có hình dạng riêng, không giống search/lookup."""
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=CHART)

    ids = await app_store_adapter(handler).chart_ids("top-free")

    assert ids == ["1617391485", "1189041808"]
    # Tên bảng dễ đọc phải dịch sang tên thật của endpoint, kèm lọc thể loại.
    assert "topfreeapplications" in urls[0]
    assert "genre=6014" in urls[0]


async def test_bang_xep_hang_khong_xin_qua_tran_da_kiem() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=CHART)

    await app_store_adapter(handler).chart_ids("top-free", limit=500)

    assert "limit=100" in urls[0]


async def test_lookup_loai_app_khong_phai_game() -> None:
    """Bảng xếp hạng đã lọc sẵn, nhưng `search` thì không: `primaryGenreId` là
    chỗ duy nhất biết được một record có phải game hay không."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LOOKUP)

    entities = await app_store_adapter(handler).details(["1189041808", "579523206"])

    assert [game.titles.primary for game in entities] == ["Liên Quân Mobile", "Free Fire"]


async def test_lookup_gop_200_id_moi_lan() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["id"].split(",")
        calls.append(len(ids))
        return httpx.Response(200, json=LOOKUP)

    await app_store_adapter(handler).details([str(i) for i in range(450)])

    assert calls == [200, 200, 50]


async def test_loi_5xx_duoc_retry_con_404_thi_khong() -> None:
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500 if attempts["n"] == 1 else 200, json=CHART)

    await app_store_adapter(flaky).chart_ids("top-free", limit=10)
    assert attempts["n"] == 2

    with pytest.raises(PermanentError):
        await app_store_adapter(lambda request: httpx.Response(404, text="no")).chart_ids(
            "top-free", limit=10
        )


# --- ánh xạ Google Play ----------------------------------------------------


def test_play_ghep_ten_anh_va_ten_viet() -> None:
    aov = PLAY_APPS["com.garena.game.kgvn"]
    game = play_to_game(aov["en"], vietnamese_name=aov["vi"]["title"])

    assert game.titles.primary == "Arena of Valor"
    assert game.titles.vi == "Liên Quân Mobile"
    assert game.external_ids.google_play == "com.garena.game.kgvn"
    assert game.platforms == ["android"]


def test_play_chi_doc_duoc_ngay_tu_payload_tieng_anh() -> None:
    """`released` của Play là chuỗi đã bản địa hoá. "18 tháng 11, 2016" không
    parse được — đoán bừa còn tệ hơn để trống."""
    aov = PLAY_APPS["com.garena.game.kgvn"]

    assert play_to_game(aov["en"]).release_dates[0].date == "2016-11-18"
    assert play_to_game(aov["vi"]).release_dates == []


def test_play_ten_hai_ngon_ngu_giong_nhau_thi_khong_ghi_titles_vi() -> None:
    ff = PLAY_APPS["com.dts.freefireth"]
    game = play_to_game(ff["en"], vietnamese_name=ff["vi"]["title"])

    assert game.titles.primary == "Free Fire"
    assert game.titles.vi is None


def play_adapter() -> GooglePlayAdapter:
    def app_fetcher(app_id: str, lang: str = "en", country: str = "vn") -> dict[str, Any]:
        if app_id not in PLAY_APPS:
            raise LookupError(f"không có {app_id}")
        payload: dict[str, Any] = PLAY_APPS[app_id][lang]
        return payload

    def search_fetcher(
        query: str, n_hits: int = 30, lang: str = "vi", country: str = "vn"
    ) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = PLAY_SEARCH
        return hits

    return GooglePlayAdapter(config(), app_fetcher=app_fetcher, search_fetcher=search_fetcher)


async def test_play_bo_hit_khong_boc_duoc_app_id() -> None:
    """Play dựng thẻ kết quả đầu bảng khác các thẻ còn lại và thư viện trả
    `appId: None` cho nó — kiểm bằng tay 2026-09-08. Không bỏ thì bước sau gọi
    `app(None)` và cả từ khoá đó hỏng."""
    app_ids = await play_adapter().search_games("liên quân")

    assert None not in app_ids
    assert app_ids == ["com.dts.freefireth", "com.zing.zalo"]


async def test_play_khong_loc_game_o_buoc_tim() -> None:
    """Kết quả `search` không có `genreId`, nên Zalo vẫn lọt qua đây; chỗ loại
    nó là `detail`, nơi payload `app()` có `genreId`."""
    app_ids = await play_adapter().search_games("liên quân")

    assert "com.zing.zalo" in app_ids
    assert await play_adapter().detail("com.zing.zalo") is None


async def test_play_lay_chi_tiet_tra_none_neu_khong_phai_game() -> None:
    assert await play_adapter().detail("com.zing.zalo") is None

    game = await play_adapter().detail("com.garena.game.kgvn")
    assert game is not None
    assert game.titles.vi == "Liên Quân Mobile"


# --- luật ghép hai store ---------------------------------------------------


def make_game(**overrides: Any) -> Game:
    base: dict[str, Any] = {
        "slug": "arena-of-valor",
        "titles": Titles(primary="Arena of Valor", vi="Liên Quân Mobile"),
        "publishers": ["Garena"],
        "external_ids": ExternalIds(app_store="1189041808"),
        "platforms": ["ios"],
    }
    return Game(**(base | overrides))


def test_ghep_khi_ca_ten_va_nha_phat_hanh_khop() -> None:
    ios = make_game()
    android = make_game(
        slug="lien-quan-mobile",
        external_ids=ExternalIds(google_play="com.garena.game.kgvn"),
        platforms=["android"],
    )

    assert is_same_game(android, ios) is True


def test_ten_khop_nhung_khac_nha_phat_hanh_thi_khong_ghep() -> None:
    """"Sudoku" của mười nhà khác nhau vẫn là mười game khác nhau."""
    ios = make_game(titles=Titles(primary="Sudoku"), publishers=["Nhà A"])
    android = make_game(
        titles=Titles(primary="Sudoku"),
        publishers=["Nhà B"],
        external_ids=ExternalIds(google_play="com.b.sudoku"),
    )

    assert is_same_game(android, ios) is False


def test_cung_nha_phat_hanh_nhung_khac_ten_thi_khong_ghep() -> None:
    """Một studio có hàng chục game."""
    ios = make_game()
    android = make_game(
        titles=Titles(primary="Free Fire"),
        external_ids=ExternalIds(google_play="com.dts.freefireth"),
    )

    assert is_same_game(android, ios) is False


def test_ten_viet_khop_voi_ten_chinh_ben_kia_cung_tinh() -> None:
    """Store này để tên tiếng Việt làm tên chính, store kia để tên tiếng Anh."""
    ios = make_game(titles=Titles(primary="Liên Quân Mobile"))
    android = make_game(
        titles=Titles(primary="Arena of Valor", vi="Liên Quân Mobile"),
        external_ids=ExternalIds(google_play="com.garena.game.kgvn"),
    )

    assert is_same_game(android, ios) is True


# --- ghi xuống Mongo -------------------------------------------------------


async def test_ghi_lan_dau_roi_chay_lai_thi_khong_doi(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game = make_game()

    assert await store_game(mongo_db, game, key="app_store") == "inserted"
    assert await store_game(mongo_db, game, key="app_store") == "unchanged"
    assert await games(mongo_db).count_documents({}) == 1


async def test_ban_android_ghep_vao_entity_ios_da_co(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    await store_game(mongo_db, make_game(), key="app_store")

    android = make_game(
        slug="lien-quan-mobile",
        external_ids=ExternalIds(google_play="com.garena.game.kgvn"),
        platforms=["android"],
    )
    outcome = await store_game(mongo_db, android, key="google_play")

    assert outcome == "linked"
    assert await games(mongo_db).count_documents({}) == 1

    doc = await games(mongo_db).find_one({})
    assert doc is not None
    assert doc["external_ids"]["app_store"] == "1189041808"
    assert doc["external_ids"]["google_play"] == "com.garena.game.kgvn"
    assert sorted(doc["platforms"]) == ["android", "ios"]
    # Slug giữ nguyên của entity cũ: nó đã nằm trên URL và trong index.
    assert doc["slug"] == "arena-of-valor"


async def test_job_store_nay_khong_xoa_du_lieu_cua_store_kia(mongo_db: Db) -> None:
    """Cái bẫy chính của mục này.

    Sau khi ghép, job Play chạy lại. Ghi đè cả document thì `external_ids.
    app_store` và platform `ios` biến mất, rồi lượt sau job App Store ghi đè
    ngược — hai job giẫm chân nhau vô tận mà lần nào cũng báo "thành công".
    """
    await ensure_indexes(mongo_db)
    await store_game(mongo_db, make_game(), key="app_store")
    android = make_game(
        slug="lien-quan-mobile",
        external_ids=ExternalIds(google_play="com.garena.game.kgvn"),
        platforms=["android"],
    )
    await store_game(mongo_db, android, key="google_play")

    # Lượt chạy thứ hai của job Play, y hệt lượt đầu.
    await store_game(mongo_db, android, key="google_play")

    doc = await games(mongo_db).find_one({})
    assert doc is not None
    assert doc["external_ids"]["app_store"] == "1189041808"
    assert "ios" in doc["platforms"]
    assert await games(mongo_db).count_documents({}) == 1


async def test_hai_game_khac_nhau_trung_ten_thi_thanh_hai_entity(mongo_db: Db) -> None:
    """Store mobile đầy game trùng tên. `slug` có index unique nên không xử lý
    là job đổ ngay ở cái thứ hai."""
    await ensure_indexes(mongo_db)
    await store_game(
        mongo_db,
        make_game(slug="sudoku", titles=Titles(primary="Sudoku"), publishers=["Nhà A"]),
        key="app_store",
    )
    outcome = await store_game(
        mongo_db,
        make_game(
            slug="sudoku",
            titles=Titles(primary="Sudoku"),
            publishers=["Nhà B"],
            external_ids=ExternalIds(google_play="com.b.sudoku"),
        ),
        key="google_play",
    )

    assert outcome == "inserted"
    slugs = sorted([doc["slug"] async for doc in games(mongo_db).find({}, {"slug": 1})])
    assert slugs == ["sudoku", "sudoku-android"]


async def test_khong_ghep_vao_entity_da_co_id_cua_chinh_store_do(mongo_db: Db) -> None:
    """Hai appId khác nhau ở CÙNG một store là hai app khác nhau, dù trùng tên
    và trùng nhà phát hành."""
    await ensure_indexes(mongo_db)
    await store_game(
        mongo_db,
        make_game(
            external_ids=ExternalIds(google_play="com.garena.aov.old"),
            platforms=["android"],
        ),
        key="google_play",
    )

    game = make_game(external_ids=ExternalIds(google_play="com.garena.game.kgvn"))
    assert await find_link_candidate(mongo_db, game, key="google_play") is None
    assert await store_game(mongo_db, game, key="google_play") == "inserted"
    assert await games(mongo_db).count_documents({}) == 2


async def test_unique_slug_dem_tiep_khi_ca_hau_to_cung_ket(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    for slug in ("ludo", "ludo-android"):
        await upsert_game(
            mongo_db,
            make_game(slug=slug, external_ids=ExternalIds(app_store=slug)),
            key="app_store",
        )

    assert await unique_slug(mongo_db, "ludo", suffix="android") == "ludo-android-2"


# --- job ------------------------------------------------------------------


def test_tu_khoa_seed_doc_duoc_va_khong_rong() -> None:
    """Danh sách từ khoá là nội dung tĩnh trong JSON. Hỏng file này thì job
    Play mất luôn nguồn khám phá cho game chỉ có trên Android."""
    terms = seed_terms()

    assert len(terms) >= 20
    assert "liên quân" in terms
    assert all(term.strip() for term in terms)


async def test_chi_do_tren_play_nhung_game_ios_chua_biet_ban_android(mongo_db: Db) -> None:
    """Cầu nối giữa hai job: game vào catalog từ App Store, job Play lấy chính
    tên đó đi tìm bản Android."""
    await ensure_indexes(mongo_db)
    await store_game(mongo_db, make_game(), key="app_store")
    await store_game(
        mongo_db,
        make_game(
            slug="free-fire",
            titles=Titles(primary="Free Fire"),
            external_ids=ExternalIds(app_store="1195621598", google_play="com.dts.freefireth"),
        ),
        key="app_store",
    )

    titles = await _titles_to_probe(mongo_db, limit=50)

    # Free Fire đã biết bản Android rồi, không cần dò lại.
    assert titles == ["Arena of Valor"]
