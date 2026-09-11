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


def bucket(
    redis: Redis,
    key: str,
    capacity: int,
    per_seconds: float,
    *,
    max_wait_seconds: float = 30.0,
    reserve: int = 0,
) -> RedisTokenBucket:
    # Khai tường minh hai kwarg thay vì `**kw: float`: `reserve` là `int`, nên
    # dạng gom lại làm `mypy app tests` đỏ ngay từ commit thêm `reserve`.
    return RedisTokenBucket(
        redis,
        key,
        RateLimit(capacity, per_seconds),
        max_wait_seconds=max_wait_seconds,
        reserve=reserve,
    )


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


# --- sàn token (reserve) ----------------------------------------------------
#
# `docs/CLAUDE.md`: "không được để một job làm cạn quota của job khác". Job bồi
# catalog gọi appdetails một request mỗi appid, tuần tự hàng trăm lần, nên nó là
# job duy nhất có thể vét sạch bucket dùng chung.


async def test_reserve_chan_nguoi_goi_o_san(redis_client: Redis) -> None:
    """Người gọi có `reserve` chỉ được dùng tới `capacity - reserve`."""
    b = bucket(redis_client, "r1", 10, 10.0, reserve=4)

    for _ in range(6):
        assert await b.try_acquire(now_ms=T0) == 0.0

    # Còn đúng 4 token trong bucket, nhưng chúng không thuộc về người gọi này.
    assert await b.try_acquire(now_ms=T0) > 0.0


async def test_job_khong_co_reserve_dung_duoc_phan_san(redis_client: Redis) -> None:
    """Chốt chính: sàn tồn tại để job KHÁC dùng, không phải để bỏ không.

    Thiếu nửa này thì `reserve` chỉ là hạ hạn mức chung — 4 token kia sẽ nằm đó
    vô dụng và cả hệ thống chạy chậm hơn mà không ai được lợi.
    """
    greedy = bucket(redis_client, "r2", 10, 10.0, reserve=4)
    other = bucket(redis_client, "r2", 10, 10.0)  # cùng key, không có sàn

    for _ in range(6):
        assert await greedy.try_acquire(now_ms=T0) == 0.0
    assert await greedy.try_acquire(now_ms=T0) > 0.0

    # Đúng 4 token còn lại, và job không đặt sàn lấy được trọn cả 4.
    for _ in range(4):
        assert await other.try_acquire(now_ms=T0) == 0.0
    assert await other.try_acquire(now_ms=T0) > 0.0


async def test_thoi_gian_cho_tinh_ca_san(redis_client: Redis) -> None:
    """Chờ tới khi vượt sàn, không phải tới khi có đủ token. Tính thiếu thì
    `acquire` tỉnh dậy quá sớm và quay vòng vô ích."""
    # 10 token / 10 giây -> 1 token/giây.
    b = bucket(redis_client, "r3", 10, 10.0, reserve=4)
    for _ in range(6):
        await b.try_acquire(now_ms=T0)

    # Còn 4, cần tới 5 mới lấy được 1 mà vẫn giữ sàn 4 -> chờ 1 giây.
    assert await b.try_acquire(now_ms=T0) == pytest.approx(1.0, abs=0.01)


async def test_xin_nhieu_hon_phan_duoc_dung_thi_bao_loi_ngay(redis_client: Redis) -> None:
    """`PermanentError` ngay, không phải chờ hết `max_wait_seconds` rồi chết mỗi
    lượt — hỏng kiểu đó trông y như lỗi mạng."""
    b = bucket(redis_client, "r4", 10, 10.0, reserve=4)

    assert await b.try_acquire(6, now_ms=T0) == 0.0  # đúng trần, vẫn qua

    with pytest.raises(PermanentError):
        await b.try_acquire(7, now_ms=T0)


async def test_reserve_khong_hop_le_bao_loi_luc_dung_bucket(redis_client: Redis) -> None:
    """`reserve == capacity` thì không request nào qua được và job chết mỗi lượt.
    Chặn ở lúc dựng, chứ không để nó biến thành một lỗi lúc chạy."""
    with pytest.raises(PermanentError):
        bucket(redis_client, "r5", 10, 10.0, reserve=10)
    with pytest.raises(PermanentError):
        bucket(redis_client, "r6", 10, 10.0, reserve=-1)


async def test_mac_dinh_khong_co_san_thi_vet_duoc_het(redis_client: Redis) -> None:
    """Hành vi cũ phải y nguyên: người gọi không đặt `reserve` dùng tới token
    cuối cùng."""
    b = bucket(redis_client, "r7", 5, 5.0)

    for _ in range(5):
        assert await b.try_acquire(now_ms=T0) == 0.0
    assert await b.try_acquire(now_ms=T0) > 0.0
