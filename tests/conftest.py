from __future__ import annotations

import json
import os
import pathlib
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from redis.asyncio import Redis

from app.models.game import Game
from app.search.meili import MeiliIndex
from app.services.catalog import with_aliases

# CI dựng một service Redis thật (xem .github/workflows/ci.yml). Máy dev không
# chạy Redis thì các test cần nó tự bỏ qua thay vì đỏ.
REDIS_TEST_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")

# CI đặt REQUIRE_REDIS=1: ở đó Redis phải có thật, thiếu là hỏng hạ tầng CI chứ
# không phải chuyện bỏ qua được. Không có cờ này thì test skip im lặng và phần
# logic quan trọng nhất coi như chưa bao giờ được kiểm.
REQUIRE_REDIS = os.getenv("REQUIRE_REDIS") == "1"

# Mongo: cùng cách nghĩ. Ràng buộc unique một phần và cơ chế "chỉ ghi khi nội
# dung đổi" không thể kiểm bằng mock — chúng là hành vi của chính Mongo.
MONGO_TEST_URI = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27017")
REQUIRE_MONGO = os.getenv("REQUIRE_MONGO") == "1"
MONGO_TEST_DB = "gamesnews_test"

# Meilisearch: chất lượng tìm kiếm tiếng Việt là checkpoint khó nhất của
# Phase 1 và không có cách nào kiểm bằng mock — nó là hành vi của tokenizer và
# của ranking rules, không phải của code ta viết.
MEILI_TEST_URL = os.getenv("TEST_MEILI_URL", "http://localhost:7700")
MEILI_TEST_KEY = os.getenv("MEILI_MASTER_KEY", "")
REQUIRE_MEILI = os.getenv("REQUIRE_MEILI") == "1"
MEILI_TEST_INDEX = "games_test"

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_game_fixtures() -> tuple[list[Game], dict[str, str]]:
    """Đọc tests/fixtures/games.json thành model `Game`.

    Trả về kèm bản đồ {slug con: slug cha}: `parent_game` là ObjectId nên chỉ
    nối được sau khi game cha đã nằm trong Mongo.

    Alias KHÔNG nằm sẵn trong JSON mà được sinh qua `with_aliases` — đúng đường
    mà job đồng bộ thật sẽ đi. Nhờ vậy test tìm kiếm kiểm luôn cả
    `normalize_vi`, chứ không kiểm một tập alias chép tay.
    """
    raw = json.loads((FIXTURES / "games.json").read_text(encoding="utf-8"))

    games: list[Game] = []
    parents: dict[str, str] = {}
    for item in raw:
        entry = dict(item)
        if parent_slug := entry.pop("parent_slug", None):
            parents[entry["slug"]] = parent_slug
        extra = entry.pop("extra_aliases", [])
        games.append(with_aliases(Game(**entry), extra))
    return games, parents


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(
        REDIS_TEST_URL,
        decode_responses=True,
        # Không có Redis thì bỏ qua cho nhanh, đừng để cả suite chờ timeout.
        socket_connect_timeout=0.5,
    )
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        message = f"không kết nối được Redis ở {REDIS_TEST_URL}: {exc}"
        if REQUIRE_REDIS:
            pytest.fail(message)
        pytest.skip(message)  # máy dev không chạy Redis -> bỏ qua, không phải lỗi test

    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def mongo_db() -> AsyncIterator[AsyncIOMotorDatabase[dict[str, object]]]:
    client: AsyncIOMotorClient[dict[str, object]] = AsyncIOMotorClient(
        MONGO_TEST_URI,
        serverSelectionTimeoutMS=500,
        tz_aware=True,
    )
    try:
        await client.admin.command("ping")
    except Exception as exc:
        client.close()
        message = f"không kết nối được Mongo ở {MONGO_TEST_URI}: {exc}"
        if REQUIRE_MONGO:
            pytest.fail(message)
        pytest.skip(message)

    # Xoá trước khi chạy chứ không chỉ sau: lần chạy trước có thể đã chết giữa
    # chừng và để lại rác, khiến test sau đỏ vì lý do chẳng liên quan.
    await client.drop_database(MONGO_TEST_DB)
    try:
        yield client[MONGO_TEST_DB]
    finally:
        await client.drop_database(MONGO_TEST_DB)
        client.close()


@pytest_asyncio.fixture
async def meili_index() -> AsyncIterator[MeiliIndex]:
    http = httpx.AsyncClient(timeout=10.0)
    # Index riêng cho test, không đụng vào index `games` của máy dev.
    index = MeiliIndex(http, MEILI_TEST_URL, MEILI_TEST_KEY, uid=MEILI_TEST_INDEX)

    try:
        response = await http.get(f"{MEILI_TEST_URL}/health")
        response.raise_for_status()
    except Exception as exc:
        await http.aclose()
        message = f"không kết nối được Meilisearch ở {MEILI_TEST_URL}: {exc}"
        if REQUIRE_MEILI:
            pytest.fail(message)
        pytest.skip(message)

    await index.delete_index()
    try:
        yield index
    finally:
        await index.delete_index()
        await http.aclose()
