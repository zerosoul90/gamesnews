"""Test hành vi của BaseAdapter qua adapter giả: retry, phân loại lỗi, hook."""

from __future__ import annotations

import pytest

from app.adapters.base import (
    AdapterConfig,
    CallRecord,
    PermanentError,
    RetryPolicy,
    TransientError,
    classify_http_status,
)
from app.adapters.dummy import DummyAdapter
from app.adapters.dummy.adapter import Scripted

OK = {"id": "1245620", "name": "Elden Ring"}


class CountingLimiter:
    """Rate limiter giả — đếm số token đã tiêu, không cần Redis."""

    def __init__(self) -> None:
        self.acquired = 0

    async def acquire(self, tokens: int = 1) -> None:
        self.acquired += tokens


def make(
    script: list[Scripted], *, max_attempts: int = 3
) -> tuple[DummyAdapter, CountingLimiter, list[CallRecord]]:
    limiter = CountingLimiter()
    records: list[CallRecord] = []
    config = AdapterConfig(
        limiter=limiter,
        # base_delay 0 để test không phải ngủ thật.
        retry=RetryPolicy(max_attempts=max_attempts, base_delay_seconds=0.0, jitter=0.0),
        hooks=[records.append],
    )
    return DummyAdapter(config, script), limiter, records


async def test_goi_thanh_cong_thi_chuan_hoa_ve_model() -> None:
    adapter, limiter, records = make([OK])

    result = await adapter.fetch(endpoint="appdetails")

    assert result.external_id == "1245620"
    assert result.title == "Elden Ring"
    assert adapter.calls == 1
    assert limiter.acquired == 1
    assert [r.ok for r in records] == [True]


async def test_loi_tam_thoi_duoc_thu_lai() -> None:
    adapter, limiter, records = make([TransientError("502"), TransientError("502"), OK])

    result = await adapter.fetch(endpoint="appdetails")

    assert result.title == "Elden Ring"
    assert adapter.calls == 3
    # Mỗi lần thử là một request thật nên phải tiêu token, kể cả lần retry.
    assert limiter.acquired == 3
    assert [r.ok for r in records] == [False, False, True]
    assert [r.attempt for r in records] == [1, 2, 3]


async def test_loi_vinh_vien_khong_thu_lai() -> None:
    adapter, limiter, records = make([PermanentError("404"), OK])

    with pytest.raises(PermanentError):
        await adapter.fetch(endpoint="appdetails")

    assert adapter.calls == 1
    assert limiter.acquired == 1
    assert len(records) == 1


async def test_het_luot_thu_thi_nem_loi_cuoi() -> None:
    adapter, _, records = make([TransientError("a"), TransientError("b"), TransientError("c")])

    with pytest.raises(TransientError, match="c"):
        await adapter.fetch(endpoint="appdetails")

    assert adapter.calls == 3
    assert len(records) == 3


async def test_loi_la_duoc_boc_thanh_loi_vinh_vien() -> None:
    """Lớp con quên phân loại thì không được retry mù — gọi lại 3 lần một lỗi
    lập trình chỉ tốn quota."""
    adapter, limiter, _ = make([ValueError("bug trong adapter")])

    with pytest.raises(PermanentError):
        await adapter.fetch(endpoint="appdetails")

    assert adapter.calls == 1
    assert limiter.acquired == 1


async def test_payload_thieu_truong_la_loi_vinh_vien() -> None:
    adapter, _, _ = make([{"id": "1"}])

    with pytest.raises(PermanentError):
        await adapter.fetch(endpoint="appdetails")


async def test_hook_ghi_du_thong_tin_de_do_quota() -> None:
    adapter, _, records = make([OK])

    await adapter.fetch(endpoint="appdetails", cost=4)

    record = records[0]
    assert record.source == "dummy"
    assert record.endpoint == "appdetails"
    assert record.cost == 4
    assert record.duration_ms >= 0


async def test_adapter_phai_khai_bao_source() -> None:
    from app.adapters.base import BaseAdapter

    class KhongCoSource(BaseAdapter[dict[str, str], str]):
        async def fetch_raw(self, **params: object) -> dict[str, str]:
            return {}

        def normalize(self, raw: dict[str, str]) -> str:
            return ""

    with pytest.raises(TypeError, match="source"):
        KhongCoSource(AdapterConfig(limiter=CountingLimiter()))


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (200, None),
        (304, None),
        (400, PermanentError),
        (401, PermanentError),
        (404, PermanentError),
        (408, TransientError),
        (429, "rate"),
        (500, TransientError),
        (503, TransientError),
    ],
)
def test_phan_loai_ma_http(status_code: int, expected: object) -> None:
    result = classify_http_status(status_code)
    if expected == "rate":
        assert result is not None and issubclass(result, TransientError)
    else:
        assert result is expected


def test_backoff_tang_theo_luy_thua() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, jitter=0.0, max_delay_seconds=10.0)
    assert [policy.delay_for(i) for i in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 8.0]
    # Có trần, không chờ vô hạn.
    assert policy.delay_for(10) == 10.0


def test_jitter_nam_trong_bien_do() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, jitter=0.25)
    delays = [policy.delay_for(1) for _ in range(200)]
    assert all(0.75 <= d <= 1.25 for d in delays)
    assert len(set(delays)) > 1  # thật sự có ngẫu nhiên
