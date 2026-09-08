"""Worker Arq. Chạy bằng: arq app.jobs.worker.WorkerSettings

`ping` là job nghiệm thu từ Phase 0. Phase 1 thêm bốn job nạp catalog: hai
cho store mobile, hai cho Steam.

Client Mongo/Redis/HTTP mở một lần trong `startup` và nằm trong `ctx`, đúng
cách API làm với lifespan: mỗi job tự mở client thì một lượt chạy nghìn app sẽ
mở nghìn kết nối.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import close_clients, create_clients
from app.core.logging import new_request_id, request_id_var, setup_logging
from app.jobs.mobile_catalog import sync_app_store, sync_google_play
from app.jobs.steam_catalog import sync_steam_app_list, sync_steam_details
from app.search.meili import MeiliIndex

logger = logging.getLogger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Job rỗng để kiểm tra worker sống và nhận được việc."""
    logger.info("job ping", extra={"job_id": ctx.get("job_id")})
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    clients = await create_clients(settings)
    ctx["clients"] = clients
    # Master key chỉ ở phía server, giống hệt bên API.
    ctx["meili"] = MeiliIndex(
        clients.http, settings.meili_url, settings.meili_master_key.get_secret_value()
    )
    logger.info("worker đã khởi động", extra={"app_env": settings.app_env})


async def shutdown(ctx: dict[str, Any]) -> None:
    if (clients := ctx.get("clients")) is not None:
        await close_clients(clients)
    logger.info("worker đã dừng")


async def on_job_start(ctx: dict[str, Any]) -> None:
    # Mỗi job có một id riêng trong log, giống request id ở tầng API.
    request_id_var.set(str(ctx.get("job_id") or new_request_id()))


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Coroutine[Any, Any, Any]]]] = [
        ping,
        sync_app_store,
        sync_google_play,
        sync_steam_app_list,
        sync_steam_details,
    ]
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    keep_result = 3600

    # arq đọc thẳng __dict__ của lớp này (arq.worker.get_kwargs), nên đây phải
    # là thuộc tính thường — để staticmethod thì arq nhận về đối tượng hàm.
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
