"""Job thu thập chỉ số và tính bảng hot — `docs/PHASE-7.md` mục 1, 4, 5.

Ba job, ba nhịp khác nhau:

- `job_fetch_steam_ccu` — 15 phút một lần, đúng độ phân giải raw mà
  `SCHEMA.md` quy định.
- `job_rollup_metrics` — mỗi giờ, gộp raw thành giờ rồi thành ngày.
- `job_compute_hotness` — mỗi giờ, chạy SAU rollup.

Cả ba trước đây đều là mock: `job_fetch_steam_ccu` chỉ ghi một dòng log,
`rollup_time_series` có TODO, còn chỉ số hot thì trả percentile viết cứng.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError
from app.adapters.steam.charts import SteamChartsAdapter
from app.core.config import get_settings
from app.services.metrics import compute_hotness, update_game_metric
from app.services.rollup import rollup_time_series

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]


def _db(ctx: dict[str, Any]) -> Db:
    """Database từ ctx của worker.

    Bản trước đọc `ctx["db"]`, mà `jobs/worker.py` chưa bao giờ đặt khoá đó —
    nó đặt `ctx["clients"]`. Job sẽ chết ngay dòng đầu với KeyError, và vì
    chưa từng chạy nên không ai thấy.
    """
    clients = ctx["clients"]
    database: Db = clients.db
    return database


async def job_rollup_metrics(ctx: dict[str, Any]) -> dict[str, int]:
    """Gộp time-series theo chính sách giữ dữ liệu của `SCHEMA.md`."""
    return await rollup_time_series(_db(ctx))


async def job_compute_hotness(ctx: dict[str, Any]) -> dict[str, int]:
    """Tính lại hai bảng xếp hạng. Chạy SAU rollup: chỉ số hot đọc mức ngày."""
    return {"games": await compute_hotness(_db(ctx))}


async def job_fetch_steam_ccu(ctx: dict[str, Any]) -> dict[str, int]:
    """Ghi CCU hiện tại của nhóm game đông người chơi nhất.

    Dùng `ISteamChartsService/GetGamesByConcurrentPlayers` (kiểm tay
    2026-09-08): **một request trả về cả bảng**, mỗi dòng có `appid`,
    `concurrent_in_game` và `peak_in_game`. So với `GetNumberOfCurrentPlayers`
    — một request một game — thì đây rẻ hơn hàng trăm lần, nên đo được nhóm
    hot mà gần như không đụng tới quota.

    Endpoint này nằm trên `api.steampowered.com`, tính hạn mức **theo key**
    (100.000 lượt/ngày), khác hẳn `store.steampowered.com` tính theo IP. Vì
    vậy nó không chia bucket `steam_appdetails` với job giá — chia nhầm chỗ thì
    job giá bị bóp vì một lý do không liên quan tới nó.
    """
    db = _db(ctx)
    settings = get_settings()
    adapter = SteamChartsAdapter(ctx["clients"].http, settings.steam_api_key.get_secret_value())

    try:
        ranks = await adapter.get_most_played()
    except AdapterError as exc:
        logger.warning("không lấy được bảng CCU", extra={"error": repr(exc)})
        return {"recorded": 0}

    if not ranks:
        return {"recorded": 0}

    # Chỉ ghi cho game đã có trong catalog: điểm đo trỏ tới một game ta không
    # biết thì không dùng được vào việc gì, mà vẫn chiếm chỗ trong time-series.
    appids = [int(r["appid"]) for r in ranks if r.get("appid") is not None]
    known: dict[int, Any] = {}
    async for doc in db.games.find(
        {"external_ids.steam_appid": {"$in": appids}},
        {"external_ids.steam_appid": 1},
    ):
        known[int(doc["external_ids"]["steam_appid"])] = doc["_id"]

    recorded = 0
    for rank in ranks:
        appid = rank.get("appid")
        ccu = rank.get("concurrent_in_game")
        if appid is None or ccu is None or int(appid) not in known:
            continue
        await update_game_metric(db, str(known[int(appid)]), "steam_ccu", int(ccu))
        recorded += 1

    logger.info(
        "ghi CCU steam",
        extra={"ranks": len(ranks), "known": len(known), "recorded": recorded},
    )
    return {"recorded": recorded}
