from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

# CI dựng một service Redis thật (xem .github/workflows/ci.yml). Máy dev không
# chạy Redis thì các test cần nó tự bỏ qua thay vì đỏ.
REDIS_TEST_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")

# CI đặt REQUIRE_REDIS=1: ở đó Redis phải có thật, thiếu là hỏng hạ tầng CI chứ
# không phải chuyện bỏ qua được. Không có cờ này thì test skip im lặng và phần
# logic quan trọng nhất coi như chưa bao giờ được kiểm.
REQUIRE_REDIS = os.getenv("REQUIRE_REDIS") == "1"


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
