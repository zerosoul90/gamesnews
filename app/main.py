"""Điểm vào của API. Hiện có /health (Phase 0), /search và /admin (Phase 1)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import admin_error_handler
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.community import router as community_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.prices import router as prices_router
from app.api.promotions import router as promotions_router
from app.api.search import router as search_router
from app.api.seo import router as seo_router
from app.api.sources import router as sources_router
from app.api.user import router as user_router
from app.api.webhooks import router as webhooks_router
from app.core.bootstrap import ensure_storage
from app.core.config import get_settings
from app.core.db import close_clients, create_clients
from app.core.logging import new_request_id, request_id_var, setup_logging
from app.services.admin import AdminError
from app.services.catalog import CatalogError

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)

    app.state.clients = await create_clients(settings)

    # Index phải có TRƯỚC lần ghi đầu tiên, không phải sau. Xem
    # `core/bootstrap.py` — trước lượt này không chỗ nào tạo chúng ở môi
    # trường thật, kể cả index unique của `games`.
    #
    # Mongo chết thì app vẫn phải lên được: `/health` mới là chỗ nói ra điều
    # đó, còn tiến trình chết lúc khởi động thì không ai đọc được gì.
    try:
        await ensure_storage(app.state.clients.db)
    except Exception:
        logger.exception("không dựng được index lúc khởi động")

    logger.info("app đã khởi động", extra={"app_env": settings.app_env})
    try:
        yield
    finally:
        await close_clients(app.state.clients)
        logger.info("app đã dừng")


app = FastAPI(title="gamesnews", version="0.1.0", lifespan=lifespan)

# `allow_origins` đọc từ cấu hình, KHÔNG viết cứng `http://localhost:4200`.
# Viết cứng thì bản deploy thật chặn đúng tên miền của chính nó, và người sửa
# sẽ bị dụ sang `["*"]` — mà `allow_credentials=True` đi cùng `*` là cấu hình
# CORS bị trình duyệt từ chối thẳng, nên "sửa" xong vẫn hỏng.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Nhận request id từ đầu vào nếu có (để lần được chuỗi gọi qua proxy),
    không thì sinh mới. Mọi dòng log trong request đều mang id này."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(search_router)
app.include_router(prices_router)
app.include_router(seo_router)
app.include_router(admin_router)
app.include_router(sources_router)
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(community_router)
app.include_router(promotions_router)
app.include_router(dashboard_router)

# Lỗi nghiệp vụ của admin là câu trả lời hợp lệ (không tìm thấy entity, hai
# entity xung đột ID), không phải sự cố máy chủ. Không đăng ký chỗ này thì
# chúng ra ngoài dưới dạng 500.
app.add_exception_handler(AdminError, admin_error_handler)
app.add_exception_handler(CatalogError, admin_error_handler)
