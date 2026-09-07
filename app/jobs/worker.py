"""Worker Arq. Chạy bằng: arq app.jobs.worker.WorkerSettings

Phase 0 chưa có job nghiệp vụ nào. Chỉ có `ping` để nghiệm thu được checkpoint
"worker kết nối được Redis và nhận job thử".
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import new_request_id, request_id_var, setup_logging

logger = logging.getLogger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Job rỗng để kiểm tra worker sống và nhận được việc."""
    logger.info("job ping", extra={"job_id": ctx.get("job_id")})
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("worker đã khởi động", extra={"app_env": settings.app_env})


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker đã dừng")


async def on_job_start(ctx: dict[str, Any]) -> None:
    # Mỗi job có một id riêng trong log, giống request id ở tầng API.
    request_id_var.set(str(ctx.get("job_id") or new_request_id()))


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Coroutine[Any, Any, Any]]]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    keep_result = 3600

    # arq đọc thẳng __dict__ của lớp này (arq.worker.get_kwargs), nên đây phải
    # là thuộc tính thường — để staticmethod thì arq nhận về đối tượng hàm.
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
