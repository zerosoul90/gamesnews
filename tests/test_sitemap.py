"""Sitemap và robots.txt — `app/api/sitemap.py`.

Checkpoint Phase 4 "Sitemap hợp lệ, Google Search Console không báo lỗi cấu
trúc" từng được đánh dấu xong trong khi `GET /sitemap.xml` trả 404.

Hai thứ đáng kiểm nhất, vì cả hai đều hỏng **im lặng** — Search Console chỉ nói
"không đọc được sitemap", không nói vì sao:

1. URL trong sitemap phải tuyệt đối và phải là origin người ngoài gọi được.
2. XML phải parse được, kể cả khi tên game chứa `&` hoặc `<`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from xml.etree import ElementTree

import pytest
from fastapi import HTTPException, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api import sitemap
from app.core.config import get_settings
from app.models.game import ExternalIds, Game, Titles
from app.services.catalog import ensure_indexes, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
BASE = "https://gamesnews.example"


@pytest.fixture
def co_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_settings` được `lru_cache` giữ, nên đặt biến môi trường thôi chưa đủ."""
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", BASE)


async def add(db: Db, slug: str, primary: str, game_type: str = "game") -> None:
    await ensure_indexes(db)
    game = with_aliases(
        Game(
            slug=slug,
            titles=Titles(primary=primary),
            type=game_type,
            external_ids=ExternalIds(steam_appid=abs(hash(slug)) % 10**6),
        )
    )
    await upsert_game(db, game, key="steam_appid")


def body(response: Response) -> str:
    """Thân phản hồi dạng chuỗi.

    `Response.body` khai kiểu là `bytes | memoryview[int]`, nên gọi thẳng
    `.decode()` là `mypy app tests` đỏ — dù ở runtime nó luôn là `bytes`.
    """
    return bytes(response.body).decode()


def locs(response: Response) -> list[str]:
    """Parse thật bằng trình đọc XML, không dò chuỗi — đó là điều bot sẽ làm."""
    # S314 tắt có chủ ý: dữ liệu vào đây là XML do chính ta vừa sinh ra trong
    # test, không phải đầu vào bên ngoài — kéo thêm `defusedxml` chỉ để đọc nó
    # là thừa.
    root = ElementTree.fromstring(body(response))  # noqa: S314
    return [el.text or "" for el in root.iter(f"{NS}loc")]


async def test_thieu_base_url_thi_bao_to_chu_khong_sinh_url_noi_bo(
    mongo_db: Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Đoán origin từ header `Host` sẽ ra `app:8000` — một sitemap đầy địa chỉ
    nội bộ nộp cho Google còn tệ hơn không có sitemap nào."""
    monkeypatch.setattr(get_settings(), "public_base_url", "")

    with pytest.raises(HTTPException) as loi:
        await sitemap.sitemap_index(mongo_db)

    assert loi.value.status_code == 503
    assert "PUBLIC_BASE_URL" in str(loi.value.detail)


async def test_robots_van_tra_loi_khi_thieu_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Khác sitemap: robots.txt hỏng nghĩa là bot không biết được đọc gì."""
    monkeypatch.setattr(get_settings(), "public_base_url", "")

    txt = body(await sitemap.robots_txt())

    assert "User-agent: *" in txt
    assert "Disallow: /admin" in txt
    assert "Sitemap:" not in txt


async def test_robots_chi_duong_toi_sitemap(co_base_url: None) -> None:
    txt = body(await sitemap.robots_txt())

    assert f"Sitemap: {BASE}/sitemap.xml" in txt


async def test_index_tro_toi_du_so_trang(mongo_db: Db, co_base_url: None) -> None:
    await add(mongo_db, "game-mot", "Game Một")

    urls = locs(await sitemap.sitemap_index(mongo_db))

    assert f"{BASE}/sitemap-pages.xml" in urls
    assert f"{BASE}/sitemap-games-1.xml" in urls


async def test_catalog_rong_van_co_mot_file_con(mongo_db: Db, co_base_url: None) -> None:
    """Index không trỏ đi đâu là cấu trúc Search Console báo lỗi."""
    urls = locs(await sitemap.sitemap_index(mongo_db))

    assert f"{BASE}/sitemap-games-1.xml" in urls


async def test_slug_game_vao_sitemap_duoi_url_tuyet_doi(mongo_db: Db, co_base_url: None) -> None:
    await add(mongo_db, "elden-ring", "ELDEN RING")

    urls = locs(await sitemap.sitemap_games(mongo_db, 1))

    assert urls == [f"{BASE}/game/elden-ring"]


async def test_dlc_khong_vao_sitemap(mongo_db: Db, co_base_url: None) -> None:
    """Vài chục nghìn trang mỏng là cách nhanh nhất để bị đánh giá thấp cả tên miền."""
    await add(mongo_db, "game-cha", "Game Cha")
    await add(mongo_db, "ban-mo-rong", "Bản Mở Rộng", game_type="dlc")

    urls = locs(await sitemap.sitemap_games(mongo_db, 1))

    assert urls == [f"{BASE}/game/game-cha"]


def test_lastmod_dung_chuan_w3c() -> None:
    """`str(datetime)` ra dấu cách thay cho `T`; Google bỏ qua mà không báo lỗi."""
    moc = dt.datetime(2026, 9, 7, 16, 28, 45, 910000, tzinfo=dt.UTC)

    assert sitemap._lastmod(moc) == "2026-09-07T16:28:45.910000+00:00"
    assert sitemap._lastmod("2026-09-07T16:28:45+00:00") == "2026-09-07T16:28:45+00:00"
    assert sitemap._lastmod("hôm qua") == ""
    assert sitemap._lastmod(None) == ""


async def test_lastmod_khong_lot_dau_cach_vao_xml(mongo_db: Db, co_base_url: None) -> None:
    """Chốt ở tầng XML, không chỉ ở hàm: `upsert_game` mới là chỗ đặt kiểu thật."""
    await add(mongo_db, "elden-ring", "ELDEN RING")

    xml = body(await sitemap.sitemap_games(mongo_db, 1))
    root = ElementTree.fromstring(xml)  # noqa: S314
    mods = [el.text or "" for el in root.iter(f"{NS}lastmod")]

    assert mods, "game vừa ghi phải có updated_at"
    for mod in mods:
        assert " " not in mod
        dt.datetime.fromisoformat(mod)


async def test_trang_ngoai_khoang_tra_404(mongo_db: Db, co_base_url: None) -> None:
    await add(mongo_db, "game-mot", "Game Một")

    for page in (0, 99):
        with pytest.raises(HTTPException) as loi:
            await sitemap.sitemap_games(mongo_db, page)
        assert loi.value.status_code == 404


async def test_trang_tinh_khop_voi_route_cua_web(co_base_url: None) -> None:
    """`/` đã 302 sang `/deals` ở server.ts — liệt kê cả hai là hai URL cùng nội dung."""
    urls = locs(await sitemap.sitemap_pages())

    assert urls == [f"{BASE}/deals", f"{BASE}/free"]
