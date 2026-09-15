"""Chốt tầng kéo feed: một nguồn hỏng không được làm hỏng lượt của nguồn khác.

`crawl_all_sources` duyệt nguồn theo thứ tự "lâu chưa crawl nhất đi trước" cho
công bằng, và Arq giết job ở 300 giây. Hai điều đó cộng lại nghĩa là thời gian
chờ MỘT nguồn phải có trần: không có trần thì nguồn treo bỏ đói mọi nguồn xếp
sau nó, lượt nào cũng thế.
"""

from __future__ import annotations

from typing import Any

import feedparser
import httpx
import pytest

from app.models.source import Source
from app.services.crawler import FEED_TIMEOUT_SECONDS, crawl_rss

FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Tin thu nghiem</title>
    <link>https://vi.du/bai-1</link>
    <description>Noi dung du dai de khong bi bo qua.</description>
  </item>
</channel></rss>
"""


def nguon(url: str = "https://vi.du/feed") -> Source:
    return Source(name="Nguon thu", url=url)


def client_tra(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_nguon_treo_khong_lam_hong_ca_luot() -> None:
    """Nguồn hết giờ thì trả danh sách rỗng, KHÔNG ném ra ngoài.

    Ném ra thì `crawl_all_sources` chết giữa chừng và mọi nguồn xếp sau mất lượt.
    """

    def treo(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("qua lau", request=request)

    async with client_tra(treo) as http:
        assert await crawl_rss(nguon(), http) == []


async def test_nguon_tra_loi_http_cung_chi_bo_qua() -> None:
    async with client_tra(lambda req: httpx.Response(503)) as http:
        assert await crawl_rss(nguon(), http) == []


async def test_moi_nguon_deu_di_kem_mot_tran_cho() -> None:
    """Không có trần thì `feedparser` chờ vô hạn — đúng lỗi đo được 2026-09-15."""
    ghi: dict[str, Any] = {}

    class GhiTimeout(httpx.AsyncClient):
        async def get(self, url: Any, **kwargs: Any) -> httpx.Response:
            ghi["timeout"] = kwargs.get("timeout")
            return httpx.Response(200, content=FEED, request=httpx.Request("GET", url))

    async with GhiTimeout() as http:
        await crawl_rss(nguon(), http)

    assert ghi["timeout"] == FEED_TIMEOUT_SECONDS


async def test_feedparser_nhan_bytes_chu_khong_tu_goi_mang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chốt chính: phần tải mạng phải nằm NGOÀI `feedparser`.

    `feedparser.parse(url)` tự tải qua `urllib` và không nhận tham số timeout
    nào — đưa URL cho nó là mất luôn đường đặt trần. Đưa bytes thì nó chỉ còn
    parse.
    """
    thay: dict[str, Any] = {}
    that = feedparser.parse

    def ghi_lai(arg: Any, *a: Any, **k: Any) -> Any:
        thay["arg"] = arg
        return that(arg, *a, **k)

    monkeypatch.setattr(feedparser, "parse", ghi_lai)

    async with client_tra(lambda req: httpx.Response(200, content=FEED)) as http:
        bai = await crawl_rss(nguon(), http)

    assert isinstance(thay["arg"], bytes), "đưa URL cho feedparser là mất đường đặt timeout"
    assert [b.title for b in bai] == ["Tin thu nghiem"]
