"""`GET /games/by-slug/{slug}` — dữ liệu cho trang `/game/:slug` của web.

Trước endpoint này web không có đường nào đi từ slug tới dữ liệu: mọi route
per-game đều nhận `game_id` là ObjectId, còn URL chỉ có slug. Nên trang chi tiết
game là HTML mock viết cứng — mọi slug đều ra "Elden Ring" giá 595.000₫.

Test đi qua ASGI app thật, không gọi thẳng hàm: gọi thẳng thì `Query("vn")`
không được phân giải và `region` vào tới Mongo nguyên dạng object `Query`, lại
cũng không kiểm được route đã đăng ký trong `main.py` hay chưa — mà quên
`include_router` thì endpoint viết đúng đến đâu cũng 404.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_db
from app.main import app
from app.models.game import ExternalIds, Game, Media, SystemRequirements, Titles
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]


@pytest_asyncio.fixture
async def client(mongo_db: Db) -> AsyncIterator[httpx.AsyncClient]:
    """Client HTTP gọi thẳng vào ASGI app, cùng event loop với fixture Mongo.

    Không dùng `TestClient`: nó chạy app trong một vòng lặp sự kiện riêng ở
    thread khác, còn client Motor của fixture lại thuộc vòng lặp của test.
    """
    app.dependency_overrides[get_db] = lambda: mongo_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def add_game(
    db: Db, slug: str, primary: str, vi: str | None = None, **kwargs: Any
) -> ObjectId:
    await ensure_indexes(db)
    game = with_aliases(
        Game(
            slug=slug,
            titles=Titles(primary=primary, vi=vi),
            external_ids=ExternalIds(steam_appid=abs(hash(slug)) % 10**6),
            **kwargs,
        )
    )
    await upsert_game(db, game, key="steam_appid")
    doc = await games(db).find_one({"slug": slug})
    assert doc is not None
    return cast(ObjectId, doc["_id"])


async def add_price(db: Db, game_id: ObjectId, store: str, final: int, **kwargs: Any) -> None:
    await db.price_current.insert_one(
        {
            "game_id": game_id,
            "store": store,
            "region": kwargs.pop("region", "vn"),
            "currency": kwargs.pop("currency", "VND"),
            "price_final": final,
            "price_initial": kwargs.pop("initial", final),
            "discount_percent": kwargs.pop("discount_percent", 0),
            "is_historical_low": kwargs.pop("is_historical_low", False),
            **kwargs,
        }
    )


async def test_slug_khong_ton_tai_thi_404(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Không phải 200 với payload rỗng: web dựa vào status này để trang trả 404
    kèm `noindex`, thay vì để bot index một slug bịa."""
    await add_game(mongo_db, "co-that", "Có Thật")

    response = await client.get("/games/by-slug/khong-he-ton-tai")

    assert response.status_code == 404


async def test_slug_co_that_thi_route_da_dang_ky(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Khoá luôn việc `games_router` có nằm trong `main.py`: thiếu
    `include_router` thì mọi test khác ở đây cũng 404, nhưng vì lý do khác hẳn
    với test ở trên — và sẽ bị đọc lẫn sang nhau."""
    await add_game(mongo_db, "portal-2", "Portal 2")

    response = await client.get("/games/by-slug/portal-2")

    assert response.status_code == 200
    assert response.json()["slug"] == "portal-2"


async def test_khong_tron_region_vao_cung_bang_gia(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Chốt chính.

    Lấy mọi region rồi sort theo `price_final` là so 199000 VND với 5 USD bằng
    phép so số: store nào báo giá bằng đồng tiền mệnh giá nhỏ sẽ luôn đứng "rẻ
    nhất", bất kể nó đắt hay rẻ thật. Bản giá US ở đây nhỏ hơn về mặt con số
    nhưng phải không xuất hiện khi hỏi region vn.
    """
    game_id = await add_game(mongo_db, "half-life", "Half-Life")
    await add_price(mongo_db, game_id, "steam", 199000, region="vn", currency="VND")
    await add_price(mongo_db, game_id, "steam", 5, region="us", currency="USD")

    body = (await client.get("/games/by-slug/half-life")).json()

    assert [p["currency"] for p in body["prices"]] == ["VND"]
    assert body["region"] == "vn"


async def test_gia_re_nhat_dung_dau(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Trang hỏi "mua ở đâu rẻ nhất", nên thứ tự là một phần của câu trả lời."""
    game_id = await add_game(mongo_db, "doom", "DOOM")
    await add_price(mongo_db, game_id, "steam", 150000)
    await add_price(mongo_db, game_id, "gog", 99000)
    await add_price(mongo_db, game_id, "epic", 120000)

    body = (await client.get("/games/by-slug/doom")).json()

    assert [p["store"] for p in body["prices"]] == ["gog", "epic", "steam"]


async def test_khong_lo_field_noi_bo(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """`aliases_normalized` là nội bộ của hệ thống khớp entity. Trả thẳng
    document thì mọi field thêm sau này tự động thành API công khai."""
    await add_game(mongo_db, "celeste", "Celeste", vi="Celeste Tiếng Việt")

    body = (await client.get("/games/by-slug/celeste")).json()

    assert "aliases_normalized" not in body
    assert "aliases" not in body
    assert body["title"] == "Celeste Tiếng Việt"  # tên tiếng Việt trước
    assert body["title_primary"] == "Celeste"


async def test_game_chua_co_gia_van_tra_ve_duoc(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Catalog cào trước, giá cào sau — khoảng giữa là trạng thái bình thường,
    không phải lỗi. Trang phải render được với bảng giá rỗng."""
    await add_game(
        mongo_db,
        "game-moi",
        "Game Mới",
        media=Media(cover="https://example.test/cover.jpg"),
        system_requirements=SystemRequirements(minimum={"os": "Windows 10"}),
    )

    body = (await client.get("/games/by-slug/game-moi")).json()

    assert body["prices"] == []
    assert body["price_history"] == []
    assert body["community_score"]["average_score"] is None
    assert body["cover_image_url"] == "https://example.test/cover.jpg"
    assert body["system_requirements"]["minimum"] == {"os": "Windows 10"}


async def test_lich_su_gia_cat_theo_history_days(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Biểu đồ 30 ngày không được kéo theo cả năm dữ liệu."""
    game_id = await add_game(mongo_db, "hades", "Hades")
    now = dt.datetime.now(dt.UTC)
    for days_ago, price in ((90, 300000), (5, 200000)):
        await mongo_db.price_history.insert_one(
            {
                "game_id": game_id,
                "region": "vn",
                "price_final": price,
                "changed_at": (now - dt.timedelta(days=days_ago)).isoformat(),
            }
        )

    body = (await client.get("/games/by-slug/hades?history_days=30")).json()

    assert [row["price_final"] for row in body["price_history"]] == [200000]
