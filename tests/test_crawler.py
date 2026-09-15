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

from app.adapters.base import USER_AGENT
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


# Khai `us-ascii` nhưng thân lại là utf-8 thật — feedparser bật `bozo` với
# `CharacterEncodingOverride` mà vẫn bóc đủ entry. Đây đúng là hình dạng feed
# của GameK, nguồn đã câm nhiều ngày vì mọi `bozo` bị coi là chí mạng.
FEED_BOZO_NHUNG_DOC_DUOC = """<?xml version="1.0" encoding="us-ascii"?>
<rss version="2.0"><channel>
  <item>
    <title>Tin tiếng Việt có dấu</title>
    <link>https://vi.du/bai-vi</link>
    <description>Nội dung tiếng Việt đủ dài để không bị bỏ qua.</description>
  </item>
</channel></rss>
""".encode()

# Trang HTML báo lỗi trả về thay cho feed: bozo, và KHÔNG entry nào.
FEED_HONG_THAT = b"<!DOCTYPE html><html><body><h1>503 Service Unavailable</h1></body></html>"

# Entry thiếu `link` — feed không chuẩn nay được nhận, nên phải chịu được nó.
FEED_THIEU_TRUONG = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Bai thieu link</title>
    <description>Noi dung du dai de khong bi bo qua.</description>
  </item>
  <item>
    <title>Bai du truong</title>
    <link>https://vi.du/bai-2</link>
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


async def test_bozo_hoi_phuc_duoc_thi_van_lay_bai() -> None:
    """`bozo` là cờ "có gì đó không chuẩn", KHÔNG phải cờ "hỏng".

    Feed khai `us-ascii` rồi gửi utf-8 thì feedparser bật `bozo` mà vẫn bóc đủ
    entry. Coi mọi `bozo` là chí mạng thì một cảnh báo về encoding là đủ để vứt
    cả feed — GameK câm nhiều ngày vì đúng chuyện này, dù 50 entry vẫn đọc được.
    """
    async with client_tra(
        lambda req: httpx.Response(200, content=FEED_BOZO_NHUNG_DOC_DUOC)
    ) as http:
        bai = await crawl_rss(nguon(), http)

    assert [b.title for b in bai] == ["Tin tiếng Việt có dấu"]


async def test_khong_boc_duoc_entry_nao_moi_la_hong() -> None:
    """Trang HTML báo lỗi trả về thay cho feed: bozo VÀ không entry nào."""
    async with client_tra(lambda req: httpx.Response(200, content=FEED_HONG_THAT)) as http:
        assert await crawl_rss(nguon(), http) == []


async def test_entry_thieu_truong_chi_bo_entry_do() -> None:
    """Nay đã nhận cả feed không chuẩn, nên một entry lỗi không được làm hỏng
    lượt của CẢ nguồn — `entry.link` thiếu thì `NewsArticle` ném AttributeError."""
    async with client_tra(lambda req: httpx.Response(200, content=FEED_THIEU_TRUONG)) as http:
        bai = await crawl_rss(nguon(), http)

    assert [b.title for b in bai] == ["Bai du truong"]


async def test_moi_nguon_deu_gui_user_agent_nhan_dang_duoc() -> None:
    """UA là bắt buộc, không phải phép lịch sự.

    Khi `feedparser` còn tự tải, nó gửi UA riêng và mọi nguồn đều nhận. Chuyển
    phần tải sang httpx làm UA thành `python-httpx/...`, và **PCGamesN chặn
    thẳng: 403** — một nguồn câm suốt mà không ai thấy, vì `crawl_all_sources`
    chỉ đếm tổng `fetched` chứ không đếm theo từng nguồn.
    """
    ghi: dict[str, Any] = {}

    def bat(request: httpx.Request) -> httpx.Response:
        ghi["ua"] = request.headers.get("User-Agent")
        return httpx.Response(200, content=FEED)

    async with client_tra(bat) as http:
        await crawl_rss(nguon(), http)

    assert ghi["ua"] == USER_AGENT
    assert "python-httpx" not in (ghi["ua"] or "")
