"""Catalog Steam — xương sống thay cho IGDB.

Fixture là payload thật ghi lại ngày 2026-09-08, không phải do tôi viết theo
trí nhớ: mục 5 đã cho thấy fixture tự dựng che mất bốn lỗi thật.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import pathlib
from typing import Any

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterConfig, PermanentError, RetryPolicy
from app.adapters.steam.adapter import SteamCatalogAdapter, parent_appid, to_game
from app.models.game import Game
from app.services import steam_queue
from app.services.catalog import ensure_indexes, games
from app.services.ingest import store_game

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
DETAILS = json.loads((FIXTURES / "steam_appdetails.json").read_text(encoding="utf-8"))
APP_LIST = json.loads((FIXTURES / "steam_applist.json").read_text(encoding="utf-8"))

ELDEN_RING = DETAILS["1245620"]["data"]
SHADOW_DLC = DETAILS["2778580"]["data"]


class CountingLimiter:
    def __init__(self) -> None:
        self.acquired = 0

    async def acquire(self, tokens: int = 1) -> None:
        self.acquired += tokens


def adapter(handler: Any, *, api_key: str = "khoa-test") -> SteamCatalogAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SteamCatalogAdapter(
        AdapterConfig(
            limiter=CountingLimiter(),
            retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0, jitter=0.0),
        ),
        http,
        api_key=api_key,
    )


# --- ánh xạ appdetails -----------------------------------------------------


def test_map_game_tu_payload_that() -> None:
    game = to_game(ELDEN_RING)

    assert game is not None
    assert game.type == "game"
    assert game.external_ids.steam_appid == 1245620
    assert game.titles.primary == "ELDEN RING"
    assert game.slug == "elden-ring"
    # Steam là một trong số ít nguồn phân biệt được studio và nhà phát hành.
    assert game.developers == ["FromSoftware, Inc."]
    assert len(game.publishers) == 2
    assert game.platforms == ["pc"]
    assert game.genres == ["action", "rpg"]


def test_doc_duoc_ngay_phat_hanh_dinh_dang_steam() -> None:
    """Steam ghi "24 Feb, 2022" — phụ thuộc tham số `l=`, nên adapter luôn gọi
    với `l=english` để cố định định dạng."""
    game = to_game(ELDEN_RING)

    assert game is not None
    assert [(rd.region, rd.date, rd.platform) for rd in game.release_dates] == [
        ("ww", "2022-02-24", "pc")
    ]


def test_dlc_nhan_dung_loai_va_tro_ve_game_cha() -> None:
    """`PHASE-1.md` mục 2 xếp "DLC phải trỏ parent_game" vào ba chỗ dễ sai."""
    game = to_game(SHADOW_DLC)

    assert game is not None
    assert game.type == "dlc"
    # Steam trả fullgame.appid dạng CHUỖI; quên ép kiểu là tra ngược trượt hết.
    assert parent_appid(SHADOW_DLC) == 1245620
    assert isinstance(SHADOW_DLC["fullgame"]["appid"], str)


def test_khong_phai_game_thi_tra_none_chu_khong_nem_loi() -> None:
    """Danh sách app của Steam lẫn nhạc nền, phần mềm, phần cứng. Bỏ qua chúng
    là chuyện bình thường, không phải sự cố cần retry."""
    for steam_type in ("music", "video", "hardware", "series", "episode"):
        assert to_game({**ELDEN_RING, "type": steam_type}) is None


def test_ngay_chua_ra_mat_thi_de_trong() -> None:
    """Steam ghi ngày sắp ra mắt đủ kiểu ("Q4 2026", "Coming soon")."""
    game = to_game({**ELDEN_RING, "release_date": {"coming_soon": True, "date": "Q4 2026"}})

    assert game is not None
    assert game.release_dates == []


def test_thieu_appid_la_loi_vinh_vien() -> None:
    payload = {k: v for k, v in ELDEN_RING.items() if k != "steam_appid"}
    with pytest.raises(PermanentError):
        to_game(payload)


# --- adapter ---------------------------------------------------------------


async def test_success_false_tra_none_chu_khong_phai_loi() -> None:
    """Cái bẫy lớn nhất của appdetails: app đã gỡ hoặc không bán ở VN vẫn trả
    HTTP 200, chỉ có `success: false` trong body. Coi đó là lỗi thì job dừng
    ngay ở app thứ mấy chục."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"1245621": {"success": False}})

    assert await adapter(handler).details(1245621) is None


async def test_lay_chi_tiet_goi_dung_gian_hang_vn_va_tieng_anh() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"1245620": DETAILS["1245620"]})

    data = await adapter(handler).details(1245620)

    assert data is not None and data["name"] == "ELDEN RING"
    assert "cc=vn" in urls[0]
    assert "l=english" in urls[0]


async def test_danh_sach_app_lat_trang_bang_last_appid() -> None:
    """Điều kiện dừng là `have_more_results`, không phải số phần tử trả về."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("last_appid", ""))
        if len(seen) == 1:
            return httpx.Response(200, json=APP_LIST)
        return httpx.Response(200, json={"response": {"apps": [], "have_more_results": False}})

    client = adapter(handler)
    apps, cursor = await client.app_list_page(0)

    assert [a.appid for a in apps] == [10, 20, 1245620]
    assert cursor == 1245620

    apps, cursor = await client.app_list_page(cursor)
    assert apps == []
    assert cursor is None
    assert seen == ["0", "1245620"]


async def test_danh_sach_app_loc_ngay_tai_nguon() -> None:
    """Lọc bằng `include_*` rẻ hơn nhiều so với tải 185k mục về rồi bỏ đi."""
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=APP_LIST)

    await adapter(handler).app_list_page(0)

    assert "include_games=true" in urls[0]
    assert "include_dlc=false" in urls[0]
    assert "include_software=false" in urls[0]


async def test_khong_co_key_thi_bao_loi_ro_rang() -> None:
    """Endpoint keyless cũ đã bị Valve gỡ, nên thiếu key là hỏng hẳn chứ không
    phải chạy chậm."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=APP_LIST)

    with pytest.raises(PermanentError, match="STEAM_API_KEY"):
        await adapter(handler, api_key="").app_list_page(0)


# --- hàng đợi --------------------------------------------------------------


async def test_hang_doi_chay_lai_khong_dat_lai_trang_thai(mongo_db: Db) -> None:
    """Đặt lại `status` thì mỗi lượt đồng bộ danh sách bắt bồi chi tiết lại từ
    đầu 185k app — với 57.600 lượt/ngày thì hàng đợi không bao giờ cạn."""
    await steam_queue.ensure_indexes(mongo_db)
    assert await steam_queue.enqueue(mongo_db, [(10, "Counter-Strike"), (20, "TFC")]) == 2

    await steam_queue.mark(mongo_db, 10, "done")
    # Lượt đồng bộ danh sách kế tiếp thấy lại đúng hai app đó.
    assert await steam_queue.enqueue(mongo_db, [(10, "Counter-Strike"), (20, "TFC")]) == 0

    assert await steam_queue.take_pending(mongo_db, 10) == [20]
    # `taken`, không còn `pending`: `take_pending` giành việc chứ không chỉ đọc.
    assert await steam_queue.counts(mongo_db) == {"done": 1, "taken": 1}


async def test_hang_doi_lay_viec_theo_appid_tang_dan(mongo_db: Db) -> None:
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(300, "c"), (100, "a"), (200, "b")])

    assert await steam_queue.take_pending(mongo_db, 2) == [100, 200]


async def test_hai_luot_chong_nhau_khong_nhan_cung_mot_app(mongo_db: Db) -> None:
    """Chốt chính.

    Bản trước chỉ `find({"status": "pending"})` rồi trả về, còn status chỉ đổi
    SAU khi xử lý xong từng app. Nên hai lượt chạy chồng nhau đọc đúng cùng một
    danh sách và cùng gọi appdetails cho cùng những app đó: gấp đôi request Steam
    cho cùng kết quả, rồi cả hai tính ra cùng một slug cho một entity mới và bên
    chậm hơn đổ `DuplicateKeyError` giữa lượt, giết cả lô.
    """
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(10, "a"), (20, "b"), (30, "c"), (40, "d")])

    first = await steam_queue.take_pending(mongo_db, 2)
    second = await steam_queue.take_pending(mongo_db, 2)

    assert first == [10, 20]
    assert second == [30, 40]
    assert not set(first) & set(second), "hai lượt nhận trùng app"


async def test_bi_gianh_mat_ung_vien_thi_lay_lo_khac_chu_khong_bo_khong(
    mongo_db: Db,
) -> None:
    """Hai lượt song song thường đọc ra cùng một tập ứng viên, nên bên chậm hơn
    mất trắng cả lô. Đo thật 2026-09-11: lượt thứ hai nhận về 0 app và bỏ không
    cả lượt cron, trong khi hàng đợi còn 180.283 mục đang chờ.
    """
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(i, f"g{i}") for i in range(1, 9)])

    first, second = await asyncio.gather(
        steam_queue.take_pending(mongo_db, 4),
        steam_queue.take_pending(mongo_db, 4),
    )

    assert not set(first) & set(second), "hai lượt nhận trùng app"
    # Chốt chính: cả hai đều có việc, không ai về tay không.
    assert first and second
    assert len(first) + len(second) == 8


async def test_het_viec_thi_luot_sau_nhan_rong(mongo_db: Db) -> None:
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(10, "a")])

    assert await steam_queue.take_pending(mongo_db, 5) == [10]
    assert await steam_queue.take_pending(mongo_db, 5) == []


async def test_loi_mang_thi_tra_viec_ve_pending(mongo_db: Db) -> None:
    """Lỗi mạng không phải bằng chứng app có vấn đề. Trước khi có cơ chế giành
    việc thì chỉ cần `continue`; giờ không trả lại là app treo tới hết lease."""
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(10, "a")])
    await steam_queue.take_pending(mongo_db, 1)

    await steam_queue.release(mongo_db, 10)

    assert await steam_queue.counts(mongo_db) == {"pending": 1}
    assert await steam_queue.take_pending(mongo_db, 1) == [10]


async def test_luot_chet_giua_duong_khong_giu_viec_vinh_vien(mongo_db: Db) -> None:
    """Không có bước thu hồi thì mỗi lần worker bị kill giữa lượt là 200 app nằm
    `taken` vĩnh viễn, và hàng đợi rò rỉ dần tới lúc không còn việc nào chạy."""
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(10, "a")])

    now = dt.datetime.now(dt.UTC)
    assert await steam_queue.take_pending(mongo_db, 1, now=now) == [10]
    # Lượt kế tiếp NGAY sau đó không được giật việc khỏi tay lượt đang chạy.
    assert await steam_queue.take_pending(mongo_db, 1, now=now) == []

    # Quá lease thì coi như lượt kia đã chết.
    sau = now + steam_queue.CLAIM_LEASE + dt.timedelta(seconds=1)
    assert await steam_queue.take_pending(mongo_db, 1, now=sau) == [10]


async def test_mark_xoa_dau_gianh_viec(mongo_db: Db) -> None:
    """Mục đã xong còn mang `claimed_by` thì `reclaim_abandoned` phải lọc thêm
    theo status, và mọi mục done mang rác vĩnh viễn."""
    await steam_queue.ensure_indexes(mongo_db)
    await steam_queue.enqueue(mongo_db, [(10, "a")])
    await steam_queue.take_pending(mongo_db, 1)

    await steam_queue.mark(mongo_db, 10, "done")

    doc = await mongo_db[steam_queue.STEAM_APPS].find_one({"_id": 10})
    assert doc is not None
    assert "claimed_by" not in doc
    assert "claimed_at" not in doc


# --- ghi vào catalog -------------------------------------------------------


async def test_ghi_game_steam_roi_chay_lai_thi_khong_doi(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    game = to_game(ELDEN_RING)
    assert game is not None

    assert await store_game(mongo_db, game, key="steam_appid") == "inserted"
    assert await store_game(mongo_db, game, key="steam_appid") == "unchanged"
    assert await games(mongo_db).count_documents({}) == 1


async def test_dlc_noi_duoc_ve_game_cha_da_co_trong_catalog(mongo_db: Db) -> None:
    from app.jobs.steam_catalog import _with_parent

    await ensure_indexes(mongo_db)
    parent = to_game(ELDEN_RING)
    dlc = to_game(SHADOW_DLC)
    assert parent is not None and dlc is not None

    await store_game(mongo_db, parent, key="steam_appid")
    linked = await _with_parent(mongo_db, dlc, SHADOW_DLC)
    await store_game(mongo_db, linked, key="steam_appid")

    parent_doc = await games(mongo_db).find_one({"external_ids.steam_appid": 1245620})
    dlc_doc = await games(mongo_db).find_one({"external_ids.steam_appid": 2778580})
    assert parent_doc is not None and dlc_doc is not None
    assert dlc_doc["parent_game"] == parent_doc["_id"]
    assert dlc_doc["type"] == "dlc"


async def test_game_cha_chua_co_thi_de_trong_chu_khong_do(mongo_db: Db) -> None:
    from app.jobs.steam_catalog import _with_parent

    await ensure_indexes(mongo_db)
    dlc = to_game(SHADOW_DLC)
    assert dlc is not None

    linked: Game = await _with_parent(mongo_db, dlc, SHADOW_DLC)

    assert linked.parent_game is None
