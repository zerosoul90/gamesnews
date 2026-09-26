"""Job thu thập chỉ số và tính bảng hot — `docs/PHASE-7.md` mục 1, 4, 5.

Ba job, ba nhịp khác nhau:

- `job_fetch_steam_ccu` — 15 phút một lần, đúng độ phân giải raw mà
  `SCHEMA.md` quy định.
- `job_fetch_tracked_ccu` — mỗi giờ, CCU từng game cho tập ngoài top 100.
- `job_rollup_metrics` — mỗi giờ, gộp raw thành giờ rồi thành ngày.
- `job_compute_hotness` — mỗi giờ, chạy SAU rollup.

Cả ba trước đây đều là mock: `job_fetch_steam_ccu` chỉ ghi một dòng log,
`rollup_time_series` có TODO, còn chỉ số hot thì trả percentile viết cứng.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError, RateLimitedError
from app.adapters.steam.charts import SteamChartsAdapter
from app.core.config import get_settings
from app.services import steam_queue
from app.services.metrics import compute_hotness, update_game_metric
from app.services.rollup import RAW, rollup_time_series

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

    # Game đông người chơi mà catalog chưa có: đẩy lên đầu hàng đợi bồi chi
    # tiết, lấy CCU làm độ ưu tiên. Không có bước này thì chúng nằm sau hơn
    # trăm nghìn appid nhỏ hơn — xem `steam_queue.prioritize`.
    missing = [
        (int(r["appid"]), int(r.get("concurrent_in_game") or 0))
        for r in ranks
        if r.get("appid") is not None and int(r["appid"]) not in known
    ]
    for missing_appid, missing_ccu in missing:
        await steam_queue.prioritize(db, [missing_appid], priority=max(missing_ccu, 1))

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
        extra={
            "ranks": len(ranks),
            "known": len(known),
            "recorded": recorded,
            "prioritized": len(missing),
        },
    )
    return {"recorded": recorded}


# Tập đo CCU từng game: game nhiều review Steam nhất. Review là thước đo độ quan
# tâm đã có sẵn cho cả catalog (`game_reviews`), còn CCU thì chính là thứ đang
# thiếu. 500 game x 24 lượt/giờ = 12.000 request/ngày.
TRACKED_LIMIT = 500

# Game đã có điểm CCU trong khoảng này — tức vừa được `job_fetch_steam_ccu` ghi
# từ bảng top 100 — thì bỏ qua: đo hai lần một game chỉ nhân đôi điểm của nó.
FRESH_WINDOW = dt.timedelta(minutes=30)


async def _tracked_games(db: Db) -> list[tuple[str, int]]:
    """(game_id, appid) của tập theo dõi, trừ game vừa có điểm CCU."""
    since = dt.datetime.now(dt.UTC) - FRESH_WINDOW
    fresh = set(
        await db[RAW].distinct("meta.game_id", {"meta.channel": "steam_ccu", "ts": {"$gte": since}})
    )
    pipeline: list[dict[str, Any]] = [
        {"$match": {"store": "steam"}},
        {"$sort": {"total": -1}},
        {"$limit": TRACKED_LIMIT},
        {"$lookup": {"from": "games", "localField": "game_id", "foreignField": "_id", "as": "g"}},
        {"$unwind": "$g"},
        {"$project": {"game_id": 1, "appid": "$g.external_ids.steam_appid"}},
    ]
    out: list[tuple[str, int]] = []
    async for doc in db.game_reviews.aggregate(pipeline):
        game_id = str(doc["game_id"])
        if doc.get("appid") is not None and game_id not in fresh:
            out.append((game_id, int(doc["appid"])))
    return out


async def job_fetch_tracked_ccu(ctx: dict[str, Any]) -> dict[str, int]:
    """CCU từng game cho tập ngoài bảng top 100.

    `job_fetch_steam_ccu` chỉ thấy top 100 game đông nhất Steam — toàn game
    đứng đầu thường trực, nên bảng "Đang tăng mạnh" gần như rỗng (đo
    2026-09-26: 59 game được xếp hạng, 9 game lên được một bậc).
    `GetNumberOfCurrentPlayers` đo được bất kỳ game nào, một request một game.

    Mỗi giờ chứ không 15 phút: chỉ số hot đọc **trung bình đỉnh theo ngày**,
    và đỉnh lấy mẫu mỗi giờ lệch rất ít so với mỗi 15 phút — CCU đổi chậm.

    Gặp 429 thì dừng lượt: endpoint không công bố hạn mức, và bắn tiếp sau 429
    chỉ tốn request mà không ghi thêm được gì.
    """
    db = _db(ctx)
    adapter = SteamChartsAdapter(ctx["clients"].http)
    tally = {"tracked": 0, "recorded": 0, "no_data": 0, "failed": 0}

    games = await _tracked_games(db)
    tally["tracked"] = len(games)
    for game_id, appid in games:
        try:
            ccu = await adapter.current_players(appid)
        except RateLimitedError:
            logger.warning("CCU từng game: gặp 429, dừng lượt", extra=tally)
            break
        except AdapterError as exc:
            tally["failed"] += 1
            logger.info("CCU từng game hỏng", extra={"appid": appid, "error": repr(exc)})
            continue
        if ccu is None:
            tally["no_data"] += 1
            continue
        await update_game_metric(db, game_id, "steam_ccu", ccu)
        tally["recorded"] += 1

    logger.info("ghi CCU từng game", extra=tally)
    return tally
