"""Giá nhiều store từ CheapShark — adapter, service lưu, và job.

`CheapSharkAdapter` có trong repo từ trước nhưng không job nào gọi, và bản cũ còn
thiếu User-Agent nên mọi lời gọi của nó đều sẽ `400`. Tới lượt này `price_current`
chỉ có `steam` và `epic`, nên bảng giá trên trang game gần như luôn một dòng.

Fixture là payload thật ghi lại 2026-09-11, gồm cả ca "appid không có trong
CheapShark" — nó trả `[]`, không phải lỗi.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import httpx
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import PermanentError, TransientError
from app.adapters.cheapshark.adapter import IDS_BATCH, USER_AGENT, CheapSharkAdapter
from app.jobs.cheapshark_pricing import sync_cheapshark_prices
from app.services.intl_prices import PRICE_INTL, ensure_indexes, intl_prices_of

Db = AsyncIOMotorDatabase[dict[str, Any]]

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PAYLOAD = json.loads((FIXTURES / "cheapshark.json").read_text(encoding="utf-8"))

STORES = PAYLOAD["stores"]
BY_APPID = PAYLOAD["by_steam_appid_1245620"]
BY_IDS = PAYLOAD["by_ids_236717_612"]
APPID_KHONG_CO = PAYLOAD["by_steam_appid_khong_co"]
BY_TITLE = PAYLOAD["by_title_batman"]


def adapter(handler: Any) -> CheapSharkAdapter:
    return CheapSharkAdapter(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def route(request: httpx.Request) -> httpx.Response:
    """Trả fixture theo đúng tham số, như API thật."""
    path = request.url.path
    params = request.url.params
    if path.endswith("/stores"):
        return httpx.Response(200, json=STORES)
    if params.get("ids"):
        wanted = params["ids"].split(",")
        return httpx.Response(200, json={k: v for k, v in BY_IDS.items() if k in wanted})
    if params.get("title"):
        return httpx.Response(200, json=BY_TITLE)
    if params.get("steamAppID") == "1245620":
        return httpx.Response(200, json=BY_APPID)
    return httpx.Response(200, json=APPID_KHONG_CO)


# --- adapter ----------------------------------------------------------------


async def test_gui_user_agent_mo_ta_duoc() -> None:
    """Chốt chính của adapter. Thiếu UA thì CheapShark trả `400` kèm
    "Missing or generic User-Agent header detected" — bản adapter trước không đặt
    header nào, nên mọi lời gọi của nó đều hỏng."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent", ""))
        return route(request)

    await adapter(handler).stores()

    assert seen == [USER_AGENT]
    # UA phải nhận dạng được client, không phải chuỗi mặc định của httpx.
    assert "GameNews" in USER_AGENT
    assert "http" in USER_AGENT


async def test_bang_ten_store() -> None:
    stores = await adapter(route).stores()

    assert stores["1"] == "Steam"
    assert stores["3"] == "GreenManGaming"
    assert stores["23"] == "GameBillet"
    assert len(stores) == 35


async def test_join_bang_steam_appid() -> None:
    """CheapShark trả sẵn `steamAppID`, nên đây là join chính xác chứ không phải
    khớp mờ theo tên như job Epic buộc phải làm."""
    assert await adapter(route).game_id_for_steam_appid(1245620) == "236717"


async def test_tra_theo_ten_cho_game_khong_co_appid_steam() -> None:
    """Đường dự phòng cho entity tới từ App Store / Google Play — chúng không có
    `steam_appid` nên `game_id_for_steam_appid` không dùng được.

    Payload thật cho thấy vì sao khớp theo tên kém chắc: cùng một truy vấn trả về
    cả Season Pass và Premium Edition, và hai bản đó có `steamAppID` là **null**.
    """
    results = await adapter(route).search_game("Batman Arkham Knight")

    assert [r["game_id"] for r in results] == ["107598", "143771", "143817"]
    assert results[0]["steam_appid"] == 208650
    # Season Pass: `steamAppID` null, không được nổ khi ép kiểu.
    assert results[1]["steam_appid"] is None
    # Cùng thang cent với `prices_for_game_ids`.
    assert results[0]["cheapest_cents"] == 320


async def test_appid_khong_co_trong_cheapshark_tra_none() -> None:
    """Trả `[]`, không phải lỗi. Coi đó là lỗi thì job dừng ở game đầu tiên mà
    CheapShark không biết."""
    assert APPID_KHONG_CO == []

    assert await adapter(route).game_id_for_steam_appid(999999999) is None


async def test_gia_tung_store_doi_sang_cent() -> None:
    """Tiền để float thì 51.59 thành 51.589999999999996 và con số đó đi thẳng vào
    giao diện."""
    result = await adapter(route).prices_for_game_ids(["236717"])

    game = result["236717"]
    assert game["currency"] == "USD"
    assert len(game["deals"]) == 10
    assert all(isinstance(deal["price_cents"], int) for deal in game["deals"])
    cheapest = game["deals"][0]
    assert cheapest["price_cents"] == 5159
    assert cheapest["retail_price_cents"] == 5999
    assert cheapest["savings_percent"] == 14


async def test_re_nhat_dung_dau() -> None:
    """Trang hỏi "mua ở đâu rẻ nhất", nên thứ tự là một phần câu trả lời."""
    result = await adapter(route).prices_for_game_ids(["236717"])

    prices = [deal["price_cents"] for deal in result["236717"]["deals"]]
    assert prices == sorted(prices)


async def test_co_link_di_mua() -> None:
    result = await adapter(route).prices_for_game_ids(["236717"])

    url = result["236717"]["deals"][0]["url"]
    assert url is not None
    assert url.startswith("https://www.cheapshark.com/redirect?dealID=")


async def test_day_lich_su_va_moc_thoi_gian() -> None:
    result = await adapter(route).prices_for_game_ids(["236717"])

    assert result["236717"]["lowest_ever_cents"] == 2995
    assert result["236717"]["lowest_ever_at"] == 1751353695


async def test_xin_qua_tran_ids_thi_bao_loi_ngay() -> None:
    """Chốt chính thứ hai.

    `ids` CẮT IM LẶNG ở 25: gửi 26 trả `200` kèm đúng 25, không lỗi nào. Tin người
    gọi ở đây là lặng lẽ mất dữ liệu, nên adapter tự chặn.
    """
    assert IDS_BATCH == 25

    with pytest.raises(PermanentError, match="25"):
        await adapter(route).prices_for_game_ids([str(i) for i in range(IDS_BATCH + 1)])


async def test_loi_mang_thanh_transient_error() -> None:
    """Lỗi mạng phải là `TransientError` để `adapters/base` cho retry. Xếp vào
    nhóm vĩnh viễn thì một lần đứt mạng làm mất cả lô."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mạng đứt")

    with pytest.raises(TransientError):
        await adapter(handler).stores()


async def test_http_400_la_loi_vinh_vien() -> None:
    """CheapShark trả `400` khi thiếu User-Agent. Retry một yêu cầu sai định dạng
    là đốt quota vô ích, nên nó phải là `PermanentError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "Missing or generic User-Agent header detected."})

    with pytest.raises(PermanentError):
        await adapter(handler).stores()


async def test_lo_rong_khong_goi_mang() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("không được gọi mạng cho lô rỗng")

    assert await adapter(handler).prices_for_game_ids([]) == {}


# --- job --------------------------------------------------------------------


class FakeClients:
    def __init__(self, db: Db, http: httpx.AsyncClient) -> None:
        self.db = db
        self.http = http
        self.redis = None


def ctx(db: Db) -> dict[str, Any]:
    return {"clients": FakeClients(db, httpx.AsyncClient(transport=httpx.MockTransport(route)))}


async def add_game(db: Db, slug: str, appid: int, **extra: Any) -> ObjectId:
    await ensure_indexes(db)
    doc: dict[str, Any] = {
        "slug": slug,
        "titles": {"primary": slug},
        "external_ids": {"steam_appid": appid, **extra},
    }
    result = await db.games.insert_one(doc)
    return ObjectId(result.inserted_id)


async def test_job_giai_game_id_roi_ghi_gia(mongo_db: Db) -> None:
    """Chốt chính của job: trước lượt này không nguồn nào cho giá nhiều store."""
    game_id = await add_game(mongo_db, "elden-ring", 1245620)

    result = await sync_cheapshark_prices(ctx(mongo_db))

    assert result["resolved"] == 1
    assert result["refreshed"] == 1

    doc = await mongo_db.games.find_one({"_id": game_id}, {"external_ids": 1})
    assert doc is not None
    assert doc["external_ids"]["cheapshark_id"] == "236717"

    stored = await intl_prices_of(mongo_db, game_id, "cheapshark")
    assert stored is not None
    assert stored["currency"] == "USD"
    assert len(stored["deals"]) == 10
    # Tên store gắn lúc ghi, không để trang phải tự dịch "23" thành "GameBillet".
    assert stored["deals"][0]["store"] == "GameBillet"
    assert stored["checked_at"]


async def test_khong_ghi_vao_price_current(mongo_db: Db) -> None:
    """Chốt quan trọng nhất về chỗ lưu.

    `/deals` truy vấn `price_current` với `{"discount_percent": {"$gt": 0}}` và
    KHÔNG lọc region. Một dòng USD lọt vào đó sẽ được trang deal render "51.59"
    thành "52₫" — sai giá trước mặt người mua.
    """
    await add_game(mongo_db, "elden-ring", 1245620)

    await sync_cheapshark_prices(ctx(mongo_db))

    assert await mongo_db.price_current.count_documents({}) == 0
    assert await mongo_db[PRICE_INTL].count_documents({}) == 1


async def test_game_cheapshark_khong_biet_thi_khong_hoi_lai_mai(mongo_db: Db) -> None:
    """`None` nghĩa là "chưa hỏi", `""` nghĩa là "hỏi rồi, không có". Thiếu phân
    biệt đó thì mỗi lượt lại tốn một request cho đúng những game không bao giờ có
    kết quả."""
    game_id = await add_game(mongo_db, "khong-co", 999999999)

    result = await sync_cheapshark_prices(ctx(mongo_db))

    assert result["unresolved"] == 1
    doc = await mongo_db.games.find_one({"_id": game_id}, {"external_ids": 1})
    assert doc is not None
    assert doc["external_ids"]["cheapshark_id"] == ""

    # Lượt sau không được coi nó là việc mới nữa.
    again = await sync_cheapshark_prices(ctx(mongo_db))
    assert again["resolved"] == 0
    assert again["unresolved"] == 0
    assert again["refreshed"] == 0


async def test_chay_lai_khong_nhan_doi_dong(mongo_db: Db) -> None:
    game_id = await add_game(mongo_db, "elden-ring", 1245620)

    await sync_cheapshark_prices(ctx(mongo_db))
    await sync_cheapshark_prices(ctx(mongo_db))

    assert await mongo_db[PRICE_INTL].count_documents({"game_id": game_id}) == 1


async def test_game_da_co_cheapshark_id_thi_khong_giai_lai(mongo_db: Db) -> None:
    game_id = await add_game(mongo_db, "elden-ring", 1245620, cheapshark_id="236717")

    result = await sync_cheapshark_prices(ctx(mongo_db))

    assert result["resolved"] == 0
    assert result["refreshed"] == 1
    assert await intl_prices_of(mongo_db, game_id, "cheapshark") is not None


async def test_chua_doc_lan_nao_tra_none(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)

    assert await intl_prices_of(mongo_db, ObjectId(), "cheapshark") is None
