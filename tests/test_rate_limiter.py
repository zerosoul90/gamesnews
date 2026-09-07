"""Test token bucket. Chạy trên Redis thật vì logic nằm trong script Lua —
giả lập Redis thì đang test bản giả, không phải thứ sẽ chạy ở production.
"""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from app.adapters.base import PermanentError, RateLimit, RateLimitedError, RedisTokenBucket

# Mốc thời gian cố định để test không phụ thuộc đồng hồ thật.
T0 = 1_700_000_000_000


def bucket(redis: Redis, key: str, capacity: int, per_seconds: float, **kw: float) -> (
    RedisTokenBucket
):
    return RedisTokenBucket(redis, key, RateLimit(capacity, per_seconds), **kw)


async def test_bucket_moi_thi_day(redis_client: Redis) -> None:
    b = bucket(redis_client, "t1", 3, 3.0)
    for _ in range(3):
        assert await b.try_acquire(now_ms=T0) == 0.0


async def test_can_bucket_thi_bao_thoi_gian_cho(redis_client: Redis) -> None:
    # 2 token / 2 giây -> 1 token/giây
    b = bucket(redis_client, "t2", 2, 2.0)
    assert await b.try_acquire(now_ms=T0) == 0.0
    assert await b.try_acquire(now_ms=T0) == 0.0

    wait = await b.try_acquire(now_ms=T0)
    assert wait == pytest.approx(1.0, abs=0.01)


async def test_nap_lai_theo_thoi_gian(redis_client: Redis) -> None:
    b = bucket(redis_client, "t3", 2, 2.0)
    await b.try_acquire(now_ms=T0)
    await b.try_acquire(now_ms=T0)
    assert await b.try_acquire(now_ms=T0) > 0

    # Sau 1 giây có đúng 1 token, không hơn.
    assert await b.try_acquire(now_ms=T0 + 1000) == 0.0
    assert await b.try_acquire(now_ms=T0 + 1000) > 0


async def test_khong_nap_qua_suc_chua(redis_client: Redis) -> None:
    b = bucket(redis_client, "t4", 2, 2.0)
    await b.try_acquire(now_ms=T0)
    await b.try_acquire(now_ms=T0)

    # Nghỉ rất lâu vẫn chỉ đầy tới capacity, không tích luỹ vô hạn.
    for _ in range(2):
        assert await b.try_acquire(now_ms=T0 + 3_600_000) == 0.0
    assert await b.try_acquire(now_ms=T0 + 3_600_000) > 0


async def test_hai_client_dung_chung_mot_bucket(redis_client: Redis) -> None:
    """Điểm quan trọng nhất: worker và API là hai tiến trình, cùng key thì
    phải cùng hạn mức. Steam giới hạn theo IP, không theo tiến trình."""
    a = bucket(redis_client, "steam:appdetails", 2, 2.0)
    b = bucket(redis_client, "steam:appdetails", 2, 2.0)

    assert await a.try_acquire(now_ms=T0) == 0.0
    assert await b.try_acquire(now_ms=T0) == 0.0
    # Tổng cộng đã tiêu 2 token của cùng một bucket.
    assert await a.try_acquire(now_ms=T0) > 0
    assert await b.try_acquire(now_ms=T0) > 0


async def test_bucket_khac_key_thi_doc_lap(redis_client: Redis) -> None:
    steam = bucket(redis_client, "steam", 1, 1.0)
    igdb = bucket(redis_client, "igdb", 1, 1.0)

    assert await steam.try_acquire(now_ms=T0) == 0.0
    assert await steam.try_acquire(now_ms=T0) > 0
    assert await igdb.try_acquire(now_ms=T0) == 0.0


async def test_xin_nhieu_hon_suc_chua_la_loi_vinh_vien(redis_client: Redis) -> None:
    b = bucket(redis_client, "t5", 2, 2.0)
    with pytest.raises(PermanentError):
        await b.try_acquire(5, now_ms=T0)


async def test_acquire_cho_roi_lay_duoc(redis_client: Redis) -> None:
    # 20 token/giây -> chờ tối đa 50ms, test vẫn nhanh.
    b = bucket(redis_client, "t6", 1, 0.05)
    await b.acquire()
    await asyncio.wait_for(b.acquire(), timeout=2.0)


async def test_acquire_qua_tran_cho_thi_bao_loi(redis_client: Redis) -> None:
    b = bucket(redis_client, "t7", 1, 3600.0, max_wait_seconds=0.05)
    await b.acquire()
    with pytest.raises(RateLimitedError):
        await b.acquire()


async def test_dung_dong_ho_redis_khi_khong_truyen_now(redis_client: Redis) -> None:
    b = bucket(redis_client, "t8", 1, 60.0)
    assert await b.try_acquire() == 0.0
    wait = await b.try_acquire()
    assert 0 < wait <= 60
