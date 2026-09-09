import logging
from typing import Any

logger = logging.getLogger(__name__)

async def job_sync_streamers(ctx: dict[str, Any]) -> None:
    """Job Arq: Lấy trạng thái của các streamer từ Twitch/YouTube nếu không dùng webhook"""
    # Nếu đang dùng webhook thì job này đóng vai trò fallback sync (cứ 5-10 phút 1 lần)
    logger.info("Fallback sync cho streamer")
    pass


async def job_renew_youtube_websub(ctx: dict[str, Any]) -> None:
    """Job Arq: Gia hạn YouTube WebSub (hết hạn sau vài ngày)"""
    logger.info("Gia hạn YouTube WebSub...")
    pass
