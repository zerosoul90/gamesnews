"""Bảng xếp hạng Steam — `app/adapters/steam/charts.py`.

`get_top_sellers_vn` từng trả `[]` **mãi mãi** mà không có gì đỏ lên:
`getappsincategory?category=topsellers&cc=vn` trả `{"status": 1}` rỗng, không
kèm `items` — tức là "thành công" theo mọi cách kiểm ta có. Fixture ở đây chép
lại đúng hai hình dạng phản hồi thật, đo tay ngày 2026-09-09.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.adapters.steam.charts import SteamChartsAdapter


def adapter_with(payload: dict[str, Any], *, api_key: str = "") -> SteamChartsAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return SteamChartsAdapter(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), api_key
    )


# Rút gọn từ phản hồi thật của /api/featuredcategories/?cc=vn — chú ý các khoá
# "0".."5" là MẢNG, nên vòng lặp dự phòng phải chịu được chúng.
FEATURED = {
    "0": [{"id": 1}],
    "specials": {"id": "cat_specials", "items": [{"id": 999}]},
    "top_sellers": {
        "id": "cat_topsellers",
        "items": [
            {"id": 3219630, "name": "Halloween: The Game", "final_price": 49500000},
            {"id": 1867240, "name": "WARDOGS", "final_price": 55450000},
        ],
    },
    "status": 1,
}


async def test_doc_dung_top_sellers() -> None:
    assert await adapter_with(FEATURED).get_top_sellers_vn() == [3219630, 1867240]


async def test_khoa_doi_ten_thi_tim_theo_id_category() -> None:
    payload = {k: v for k, v in FEATURED.items() if k != "top_sellers"}
    payload["ten_moi_nao_do"] = FEATURED["top_sellers"]

    assert await adapter_with(payload).get_top_sellers_vn() == [3219630, 1867240]


async def test_status_khac_1_thi_tra_rong() -> None:
    assert await adapter_with({"status": 0}) .get_top_sellers_vn() == []


async def test_khong_tim_thay_thi_tra_rong_khong_no() -> None:
    """Tầng hot còn hai nguồn tín hiệu khác; bảng xếp hạng chỉ là gia vị."""
    assert await adapter_with({"status": 1, "specials": {"items": []}}).get_top_sellers_vn() == []


async def test_ccu_yeu_cau_key() -> None:
    assert await adapter_with({}, api_key="").get_most_played() == []


async def test_ccu_doc_dung_ranks() -> None:
    payload = {"response": {"ranks": [{"rank": 1, "appid": 730, "concurrent_in_game": 1_000_000}]}}
    ranks = await adapter_with(payload, api_key="k").get_most_played()

    assert ranks[0]["appid"] == 730
