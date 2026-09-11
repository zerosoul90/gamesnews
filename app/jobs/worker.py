"""Worker Arq. Chạy bằng: arq app.jobs.worker.WorkerSettings

`ping` là job nghiệm thu từ Phase 0. Phase 1 thêm bốn job nạp catalog (hai cho
store mobile, hai cho Steam), rồi Phase 2-7 nối thêm giá, digest, chỉ số và
streamer. Phase 6 thêm `crawl_all_sources` và `sync_game_embeddings` — hai job
này trước đây **không tồn tại**, nên toàn bộ mảnh ghép tin tức có sẵn mà chưa
lần nào chạy.

Client Mongo/Redis/HTTP mở một lần trong `startup` và nằm trong `ctx`, đúng
cách API làm với lifespan: mỗi job tự mở client thì một lượt chạy nghìn app sẽ
mở nghìn kết nối.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.cron import CronJob, cron

from app.core.bootstrap import ensure_storage
from app.core.config import get_settings
from app.core.db import close_clients, create_clients
from app.core.deps import build_meili
from app.core.logging import new_request_id, request_id_var, setup_logging
from app.jobs.cheapshark_pricing import sync_cheapshark_prices
from app.jobs.embeddings import sync_game_embeddings
from app.jobs.epic_pricing import sync_epic_free_games
from app.jobs.metrics import job_compute_hotness, job_fetch_steam_ccu, job_rollup_metrics
from app.jobs.mobile_catalog import sync_app_store, sync_google_play
from app.jobs.news import crawl_all_sources
from app.jobs.notification_digest import send_notification_digest
from app.jobs.steam_catalog import sync_steam_app_list, sync_steam_details
from app.jobs.steam_pricing import recompute_price_tiers, sync_steam_prices
from app.jobs.steam_reviews import sync_steam_reviews
from app.jobs.streamer import job_renew_youtube_websub, job_sync_streamers

logger = logging.getLogger(__name__)


async def ping(ctx: dict[str, Any]) -> str:
    """Job rỗng để kiểm tra worker sống và nhận được việc."""
    logger.info("job ping", extra={"job_id": ctx.get("job_id")})
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    # Trần thời gian rộng hơn API: `/health` chậm 2 giây là hỏng, còn một job
    # đẩy batch nghìn document sang Meilisearch mất vài giây là bình thường.
    # Dùng chung trần của /health thì job đứt giữa chừng.
    clients = await create_clients(settings, timeout_seconds=settings.job_timeout_seconds)
    ctx["clients"] = clients
    # Master key chỉ ở phía server, giống hệt bên API.
    ctx["meili"] = build_meili(clients, settings)
    # Worker hay khởi động TRƯỚC API (compose không ràng buộc thứ tự giữa hai
    # cái), và job đầu tiên chạy có thể ghi trước khi API kịp dựng index. Dựng
    # ở cả hai chỗ; `ensure_storage` chạy lại được nên không hại gì.
    try:
        await ensure_storage(clients.db, ctx["meili"])
    except Exception:
        logger.exception("không dựng được index lúc khởi động worker")

    logger.info("worker đã khởi động", extra={"app_env": settings.app_env})


async def shutdown(ctx: dict[str, Any]) -> None:
    if (clients := ctx.get("clients")) is not None:
        await close_clients(clients)
    logger.info("worker đã dừng")


async def on_job_start(ctx: dict[str, Any]) -> None:
    # Mỗi job có một id riêng trong log, giống request id ở tầng API.
    request_id_var.set(str(ctx.get("job_id") or new_request_id()))


# --- Lịch chạy ---------------------------------------------------------------
#
# Trước lượt này `WorkerSettings` **không có `cron_jobs`**, nên không job nào tự
# chạy: mọi thứ phải enqueue bằng tay. Nghĩa là cả cơ chế phân tầng giá lẫn job
# gia hạn WebSub — cái mà `PHASE-7.md` cảnh báo "quên thì thông báo im lặng
# chết" — chưa từng chạy lần nào ngoài lúc có người gõ lệnh.
#
# **Giờ ở đây là UTC**: arq đọc đồng hồ của tiến trình, và container mặc định
# chạy UTC. Giờ VN = UTC + 7.
#
# `unique=True` (mặc định) là chốt quan trọng khi chạy nhiều worker: cùng một
# lượt cron chỉ một worker nhận, không phải mỗi worker một lượt.
EVERY_15_MIN = {0, 15, 30, 45}

CRON_JOBS: list[CronJob] = [
    # --- Giá (Phase 2) ---
    # Job tự dừng khi bucket Steam cạn token, nên chạy dày không hại: nó lấy
    # đúng phần quota còn thừa sau khi job catalog đã dùng.
    cron(sync_steam_prices, minute=EVERY_15_MIN),
    # Tầng đổi chậm; tính lại mỗi ngày là đủ.
    cron(recompute_price_tiers, hour=3, minute=30),
    # Epic đổi game tặng lúc 15:00 UTC thứ năm, nhưng chạy mỗi giờ chứ không
    # canh đúng mốc đó: một lượt hỏng vào đúng giờ đổi sẽ làm cả tuần thiếu
    # game free, mà đây cũng chỉ là MỘT request sau CDN.
    cron(sync_epic_free_games, minute=10),
    # Giá USD nhiều store. Nguồn riêng với hạn mức riêng nên không tranh bucket
    # `steam_appdetails`; đặt lệch giờ chỉ để log dễ đọc.
    cron(sync_cheapshark_prices, minute={12, 42}),
    # --- Catalog (Phase 1) ---
    # Bồi chi tiết 185k app mất vài ngày, nên phải chạy đều đặn và liên tục.
    cron(sync_steam_details, minute={5, 20, 35, 50}),
    # Điểm review đổi chậm hơn giá nhiều, và job tự dừng khi bucket Steam cạn —
    # đặt lệch khỏi các mốc của job giá để không hai job cùng xông vào bucket.
    cron(sync_steam_reviews, minute={8, 38}),
    # Danh sách app đầy đủ đổi chậm; kéo lại mỗi tuần.
    cron(sync_steam_app_list, weekday="sun", hour=2, minute=0),
    cron(sync_app_store, weekday="sun", hour=4, minute=0),
    cron(sync_google_play, weekday="sun", hour=5, minute=0),
    # --- Tin tức (Phase 6) ---
    # Checkpoint: "tin quốc tế lên feed tiếng Việt trong 2 giờ". 15 phút một
    # lượt cho biên rộng rãi kể cả khi vài lượt hỏng.
    cron(crawl_all_sources, minute=EVERY_15_MIN),
    # Nạp vector cho entity mới. Mỗi lượt có trần lô nên nó gặm dần.
    cron(sync_game_embeddings, minute=25),
    # --- Chỉ số & streamer (Phase 7) ---
    cron(job_fetch_steam_ccu, minute=EVERY_15_MIN),
    cron(job_rollup_metrics, minute=5),
    # SAU rollup: chỉ số hot đọc mức ngày mà rollup vừa dựng.
    cron(job_compute_hotness, minute=20),
    cron(job_sync_streamers, minute=40),
    # Lease của hub tối đa 10 ngày, và `RENEW_BEFORE` là 2 ngày. Chạy 6 giờ một
    # lượt để một lượt hỏng vẫn còn nhiều lượt sau cứu được.
    cron(job_renew_youtube_websub, hour={0, 6, 12, 18}, minute=10),
    # --- Thông báo (Phase 3) ---
    # 09:00 giờ VN = 02:00 UTC. Digest là thứ đọc lúc ngủ dậy, không phải lúc
    # nửa đêm.
    cron(send_notification_digest, hour=2, minute=0),
]


class WorkerSettings:
    functions: ClassVar[list[Callable[..., Coroutine[Any, Any, Any]]]] = [
        ping,
        sync_app_store,
        sync_google_play,
        sync_steam_app_list,
        sync_steam_details,
        sync_steam_prices,
        recompute_price_tiers,
        sync_epic_free_games,
        sync_cheapshark_prices,
        sync_steam_reviews,
        send_notification_digest,
        job_rollup_metrics,
        job_fetch_steam_ccu,
        job_compute_hotness,
        job_sync_streamers,
        job_renew_youtube_websub,
        crawl_all_sources,
        sync_game_embeddings,
    ]
    cron_jobs: ClassVar[list[CronJob]] = CRON_JOBS
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    keep_result = 3600

    # arq đọc thẳng __dict__ của lớp này (arq.worker.get_kwargs), nên đây phải
    # là thuộc tính thường — để staticmethod thì arq nhận về đối tượng hàm.
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
