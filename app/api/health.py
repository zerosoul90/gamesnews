"""GET /health — ping thật cả bốn kho, nhưng chỉ phụ thuộc bắt buộc mới
quyết định mã HTTP. Xem bảng ở `docs/PHASE-0.md` mục 4.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.deps import ClientsDep, SettingsDep

router = APIRouter(tags=["health"])

# Phụ thuộc bắt buộc: hỏng thì /health trả 503.
#
# Qdrant **không** nằm trong tập này, dù Phase 6 đã bắt đầu, vì hai lý do:
#
# 1. Chưa có gì đọc Qdrant thật. `services/entity_matcher.embedding_match` vẫn
#    là stub trả thẳng (None, 0.0) — bật cờ bắt buộc lúc này là tự nhận mình
#    chết vì một kho dữ liệu chưa ai gọi tới.
# 2. Kể cả khi Phase 6 chạy thật: Qdrant chỉ phục vụ gắn entity cho tin tức.
#    Nó chết thì tìm kiếm, catalog và giá vẫn chạy. Trả 503 là để load balancer
#    rút cả API ra khỏi vòng phục vụ — tắt toàn bộ trang vì một nhánh phụ.
#
# Khi nào embedding match chạy thật và có nhánh nào KHÔNG dùng được nếu thiếu
# Qdrant, hãy làm mịn hơn: báo `degraded` cho riêng nhánh đó, đừng 503 cả app.
REQUIRED: frozenset[str] = frozenset({"mongo", "redis", "meilisearch"})


class DependencyStatus(BaseModel):
    status: str  # "ok" | "down"
    required: bool
    latency_ms: float
    error: str | None = None


class HealthResponse(BaseModel):
    # ok        — tất cả xanh
    # degraded  — chỉ phụ thuộc không bắt buộc hỏng, API vẫn phục vụ được
    # unhealthy — có phụ thuộc bắt buộc hỏng
    status: str
    checks: dict[str, DependencyStatus]


async def _probe(
    name: str, ping: Callable[[], Awaitable[object]], timeout_seconds: float
) -> tuple[str, DependencyStatus]:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_seconds):
            await ping()
    except Exception as exc:  # kho nào hỏng cũng chỉ quy về "down"
        return name, DependencyStatus(
            status="down",
            required=name in REQUIRED,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            # Chỉ lấy loại lỗi + thông điệp ngắn; không phơi chuỗi kết nối.
            error=f"{type(exc).__name__}: {exc}"[:200] or type(exc).__name__,
        )
    return name, DependencyStatus(
        status="ok",
        required=name in REQUIRED,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response, clients: ClientsDep, settings: SettingsDep
) -> HealthResponse:
    timeout = settings.health_timeout_seconds

    probes = [
        _probe("mongo", lambda: clients.mongo.admin.command("ping"), timeout),
        _probe("redis", clients.redis.ping, timeout),
        _probe("meilisearch", lambda: clients.http.get(f"{settings.meili_url}/health"), timeout),
        _probe("qdrant", lambda: clients.http.get(f"{settings.qdrant_url}/readyz"), timeout),
    ]
    checks = dict(await asyncio.gather(*probes))

    down = [name for name, check in checks.items() if check.status == "down"]
    if any(name in REQUIRED for name in down):
        overall = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif down:
        overall = "degraded"
    else:
        overall = "ok"

    return HealthResponse(status=overall, checks=checks)
