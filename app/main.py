"""Điểm vào của API. Hiện có /health (Phase 0) và /search (Phase 1)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.health import router as health_router
from app.api.search import router as search_router
from app.core.config import get_settings
from app.core.db import close_clients, create_clients
from app.core.logging import new_request_id, request_id_var, setup_logging

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)

    app.state.clients = await create_clients(settings)
    logger.info("app đã khởi động", extra={"app_env": settings.app_env})
    try:
        yield
    finally:
        await close_clients(app.state.clients)
        logger.info("app đã dừng")


app = FastAPI(title="gamesnews", version="0.1.0", lifespan=lifespan)


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
app.include_router(search_router)
