"""Test token bucket. Chạy trên Redis thật vì logic nằm trong script Lua —
giả lập Redis thì đang test bản giả, không phải thứ sẽ chạy ở production.
"""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from app.adapters.base import (
    PermanentError,
    RateLimit,
    RateLimitedError,
    RedisDailyBudget,
    RedisTokenBucket,
)

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


# --- Trần NGÀY -------------------------------------------------------------
#
# Chiều thứ hai của cùng một quota, và nó KHÔNG suy ra được từ chiều nhịp. Ngày
# 2026-09-15 đo được `generateContent` free tier là 500 lời gọi/ngày, trong khi
# cấu hình khi ấy cho phép 1.320 — vì trần ngày đang được "canh" bằng phép nhân
# trần-mỗi-lượt nhân số-lượt-cron, một phép nhân phụ thuộc file khác và đã sai hai
# lần trong cùng một ngày.


def ngan_sach(
    redis: Redis, key: str, limit: int, *, reserve: int = 0
) -> RedisDailyBudget:
    return RedisDailyBudget(redis, key, limit, reserve=reserve)


async def test_dem_tich_luy_roi_chan_dung_tran(redis_client: Redis) -> None:
    ns = ngan_sach(redis_client, "d1", 3)
    for _ in range(3):
        await ns.spend()
    assert await ns.used() == 3

    with pytest.raises(RateLimitedError, match="hết hạn mức NGÀY"):
        await ns.spend()


async def test_san_chua_phan_cuoi_cho_nguoi_goi_khac(redis_client: Redis) -> None:
    """Không có sàn thì một đêm dịch bù vét sạch hạn mức, và sáng hôm sau không
    tin mới nào được dịch."""
    bu = ngan_sach(redis_client, "d2", 10, reserve=7)
    for _ in range(3):
        await bu.spend()
    with pytest.raises(RateLimitedError):
        await bu.spend()

    # Người gọi không đặt sàn vẫn dùng được tới lời gọi cuối — đó là mục đích
    # của sàn: phần ấy dành cho họ.
    crawl = ngan_sach(redis_client, "d2", 10)
    for _ in range(7):
        await crawl.spend()
    assert await crawl.used() == 10


async def test_hai_nguoi_goi_chung_mot_bo_dem(redis_client: Redis) -> None:
    """Chung quota thật thì phải chung bộ đếm, nếu không mỗi bên tưởng mình còn
    nguyên trần và tổng vượt gấp đôi."""
    a = ngan_sach(redis_client, "d3", 4)
    b = ngan_sach(redis_client, "d3", 4)
    await a.spend()
    await b.spend(2)
    assert await a.used() == 3
    await b.spend()
    with pytest.raises(RateLimitedError):
        await a.spend()


async def test_xin_nhieu_hon_phan_con_lai_thi_khong_tru_gi(redis_client: Redis) -> None:
    """Từ chối phải là nguyên tử: trừ một phần rồi mới báo lỗi thì bộ đếm trôi
    dần khỏi số thật sau mỗi lần bị từ chối."""
    ns = ngan_sach(redis_client, "d4", 5)
    await ns.spend(3)
    with pytest.raises(RateLimitedError):
        await ns.spend(3)
    assert await ns.used() == 3


async def test_tu_choi_cau_hinh_vo_nghia(redis_client: Redis) -> None:
    with pytest.raises(PermanentError):
        ngan_sach(redis_client, "d5", 0)
    with pytest.raises(PermanentError):
        ngan_sach(redis_client, "d5", 5, reserve=5)


def test_san_nho_hon_tran_ngay() -> None:
    """Sàn >= trần thì job dịch bù không bao giờ gọi được lời nào."""
    from app.adapters.llm.gemini import (
        GENERATE_DAILY_LIMIT,
        GENERATE_DAILY_RESERVE_FOR_CRAWL,
    )

    assert 0 < GENERATE_DAILY_RESERVE_FOR_CRAWL < GENERATE_DAILY_LIMIT


def test_tran_ngay_khong_vuot_con_so_do_duoc() -> None:
    """500 là con số Google khai trong thân 429 ngày 2026-09-15. Bộ đếm của ta
    sang ngày theo mốc UTC còn họ theo mốc khác, nên phải chừa biên."""
    from app.adapters.llm.gemini import GENERATE_DAILY_LIMIT

    assert GENERATE_DAILY_LIMIT < 500
