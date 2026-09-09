import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.rollup import rollup_time_series

logger = logging.getLogger(__name__)

async def job_rollup_metrics(ctx: dict[str, Any]) -> None:
    """Job Arq: Chạy rollup time-series mỗi giờ"""
    db: AsyncIOMotorDatabase[dict[str, Any]] = ctx["db"]
    await rollup_time_series(db)


async def job_fetch_steam_ccu(ctx: dict[str, Any]) -> None:
    """Job Arq: Kéo CCU của game từ Steam Charts"""
    # Dummy mock
    logger.info("Fetching Steam CCU...")
    pass
