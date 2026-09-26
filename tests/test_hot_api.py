"""API hai bảng xếp hạng — `docs/PHASE-9.md` mục A1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_db
from app.main import app
from app.services.metrics import HOTNESS

Db = AsyncIOMotorDatabase[dict[str, Any]]


@pytest_asyncio.fixture
async def client(mongo_db: Db) -> AsyncIterator[httpx.AsyncClient]:
    app.dependency_overrides[get_db] = lambda: mongo_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def seed(db: Db) -> dict[str, ObjectId]:
    """Dota 2 đứng đầu và đứng yên; Tân Binh nhỏ nhưng đang lên."""
    rows = [
        # Dao động của trung bình cửa sổ, không phải đổi hạng — số đo thật.
        ("dota-2", "Dota 2", None, 1.0, 0.0016, 700_000),
        ("counter-strike-2", "Counter-Strike 2", None, 0.98, 0.0, 1_300_000),
        ("tan-binh", "Rookie Game", "Tân Binh", 0.4, 0.5, 5_000),
        ("dang-len", "Climber", None, 0.5, 0.34, 9_000),
    ]
    ids: dict[str, ObjectId] = {}
    for slug, primary, vi, absolute, momentum, ccu in rows:
        game_id = ObjectId()
        ids[slug] = game_id
        await db.games.insert_one(
            {"_id": game_id, "slug": slug, "titles": {"primary": primary, "vi": vi}}
        )
        await db[HOTNESS].insert_one(
            {
                "game_id": str(game_id),
                "score_absolute": absolute,
                "score_momentum": momentum,
                "ccu_now": ccu,
                "computed_at": "2026-09-26T16:20:00+00:00",
            }
        )
    await db.price_current.insert_one(
        {
            "game_id": ids["tan-binh"],
            "store": "steam",
            "region": "vn",
            "price_final": 99_000,
            "discount_percent": 50,
            "is_historical_low": True,
        }
    )
    return ids


async def test_bang_pho_bien_xep_theo_diem_hien_tai(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    await seed(mongo_db)

    body = (await client.get("/hot", params={"board": "popular"})).json()

    assert [g["game_details"]["slug"] for g in body["games"]] == [
        "dota-2",
        "counter-strike-2",
        "dang-len",
        "tan-binh",
    ]
    assert [g["rank"] for g in body["games"]] == [1, 2, 3, 4]
    assert body["computed_at"] == "2026-09-26T16:20:00+00:00"


async def test_bang_dang_tang_khong_co_game_dung_yen(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    """Checkpoint Phase 7: bảng này không bị game top thường trực chiếm chỗ.

    Bốn game thì một bậc hạng là 1/3 percentile; Dota 2 nhích 0.0016 không lọt.
    """
    await seed(mongo_db)

    body = (await client.get("/hot", params={"board": "rising"})).json()

    assert [g["game_details"]["slug"] for g in body["games"]] == ["tan-binh", "dang-len"]


async def test_the_game_co_ten_viet_va_gia_vnd(client: httpx.AsyncClient, mongo_db: Db) -> None:
    await seed(mongo_db)

    body = (await client.get("/hot", params={"board": "rising"})).json()
    tan_binh = body["games"][0]

    assert tan_binh["game_details"]["title"] == "Tân Binh"
    assert tan_binh["price"] == {
        "price_final": 99_000,
        "discount_percent": 50,
        "is_historical_low": True,
    }
    assert body["games"][1]["price"] is None


async def test_bo_dong_tro_toi_game_da_roi_catalog(client: httpx.AsyncClient, mongo_db: Db) -> None:
    ids = await seed(mongo_db)
    await mongo_db.games.delete_one({"_id": ids["dota-2"]})

    body = (await client.get("/hot")).json()

    assert body["games"][0]["game_details"]["slug"] == "counter-strike-2"
    assert body["games"][0]["rank"] == 1


async def test_bang_khong_ton_tai_thi_422(client: httpx.AsyncClient) -> None:
    assert (await client.get("/hot", params={"board": "trending"})).status_code == 422
