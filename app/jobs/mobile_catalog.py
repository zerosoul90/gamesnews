"""Hai job nạp catalog mobile — `docs/PHASE-1.md` mục 5.

Tài liệu yêu cầu "chạy tách job, có thể lỗi mà không làm hỏng job IGDB", nên
mỗi store là một job Arq riêng: App Store hỏng thì Google Play vẫn chạy, và cả
hai đều không đụng gì tới job đồng bộ IGDB sau này.

Trong một job, **một app hỏng không được làm hỏng cả lượt chạy**. Store mobile
có hàng nghìn app với dữ liệu đủ kiểu dị dạng; dừng ở app thứ 40 vì nó thiếu
`title` thì 960 app còn lại không bao giờ vào catalog. Lỗi từng app được đếm và
ghi log, lỗi ở tầng adapter (mạng chết, bị chặn IP) mới cho nổ ra ngoài.

Thứ tự chạy có ý nghĩa: App Store trước, Google Play sau. Bảng xếp hạng của
Apple là nguồn khám phá duy nhất có thật (Google không có API xếp hạng), nên
job Play dùng chính tên game mà job App Store vừa nạp để đi tìm bản Android —
và đó cũng là lúc hai bản được ghép về một entity.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import time
from collections.abc import Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.app_store.adapter import (
    CHART_LIMIT,
    AppStoreAdapter,
    Feed,
    with_international_name,
)
from app.adapters.app_store.adapter import RATE_LIMIT as APP_STORE_RATE
from app.adapters.base import AdapterConfig, AdapterError, RateLimitedError, RedisTokenBucket
from app.adapters.google_play.adapter import RATE_LIMIT as PLAY_RATE
from app.adapters.google_play.adapter import GooglePlayAdapter
from app.models.game import Game
from app.services.catalog import games
from app.services.ingest import StoreOutcome, store_game
from app.services.search_index import reindex

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Bảng xếp hạng game của gian hàng VN. Chỉ endpoint RSS đời cũ lọc được theo
# thể loại — xem adapter. Đây là nguồn phụ; nguồn chính là search theo từ khoá.
FEEDS: tuple[Feed, ...] = ("top-free", "top-paid", "top-grossing")

# Mỗi từ khoá lấy 30 kết quả. Con số nhỏ là có chủ ý: kết quả càng sâu càng
# loãng, mà mỗi app còn tốn thêm hai request nữa ở bước lấy chi tiết.
SEARCH_HITS = 30

# Trần số game iOS đem đi dò trên Play mỗi lượt. Trần thật là `PLAY_RUN_BUDGET`
# bên dưới — con số này chỉ chặn việc kéo cả nghìn tên về bộ nhớ một lúc.
CROSS_STORE_LIMIT = 300

# Job Play dừng nhận việc mới sau chừng này giây, và ghi từng game ngay khi lấy
# xong chi tiết.
#
# Đo ngày 2026-09-26: bản cũ gom 28 từ khoá + 300 tên iOS = 328 lượt search,
# riêng bước đó ở 1 request/giây đã quá trần `job_timeout` 300s của arq — và
# game chỉ được ghi SAU khi lấy xong chi tiết của tất cả. Job chết mỗi lượt
# trước khi ghi được game nào: cả catalog có đúng 4 game mang `google_play`, đều
# là seed tay ngày 2026-09-07.
#
# 240s chừa 60s cho request đang bay, reindex cuối, và độ lệch đồng hồ. Trần
# timeout của cron đặt ở `worker.py` theo con số này.
PLAY_RUN_BUDGET = 240.0

# Một app / một tên đã dò thì bao lâu sau mới dò lại. Thiếu sổ này thì lượt nào
# cũng bắt đầu lại từ đầu danh sách và không bao giờ đi quá 240 giây đầu tiên.
PLAY_RECHECK = dt.timedelta(days=30)
PLAY_APPS = "play_apps"
PLAY_PROBES = "play_probes"

# Từ khoá seed ("liên quân", "game bắn súng"...) là để khám phá game mới trên
# Play, nên dò lại dày hơn tên iOS — nhưng không phải mỗi lượt.
SEED_RECHECK = dt.timedelta(days=7)

_SEED_TERMS_FILE = pathlib.Path(__file__).with_name("mobile_seed_terms.json")


def seed_terms() -> list[str]:
    """Từ khoá tìm trên Play. Nội dung tĩnh nằm ở JSON, không nhúng vào code."""
    payload = json.loads(_SEED_TERMS_FILE.read_text(encoding="utf-8"))
    return [str(term) for term in payload["terms"]]


class Tally(dict[str, int]):
    """Đếm kết quả từng app để cuối job có một dòng log nói được chuyện gì."""

    def add(self, outcome: StoreOutcome | str) -> None:
        self[outcome] = self.get(outcome, 0) + 1


async def _store_all(db: Db, entities: list[Game], *, key: str) -> Tally:
    tally = Tally()
    for game in entities:
        try:
            tally.add(await store_game(db, game, key=key))
        except Exception as exc:
            # Một app dị dạng không được chặn 900 app còn lại.
            tally.add("failed")
            logger.warning(
                "không ghi được game mobile",
                extra={"slug": game.slug, "key": key, "error": repr(exc)},
            )
    return tally


async def sync_app_store(ctx: dict[str, Any]) -> dict[str, int]:
    """Bảng xếp hạng gian hàng VN -> catalog."""
    clients = ctx["clients"]
    db: Db = clients.db
    started = dt.datetime.now(dt.UTC)

    adapter = AppStoreAdapter(
        AdapterConfig(limiter=RedisTokenBucket(clients.redis, "app_store", APP_STORE_RATE)),
        clients.http,
    )

    # Bảng xếp hạng chỉ cho ~300 game, nên là nguồn phụ. Nguồn chính là search
    # theo từ khoá — cùng danh sách từ khoá mà job Play dùng.
    ids: dict[str, None] = {}
    for feed in FEEDS:
        try:
            for store_id in await adapter.chart_ids(feed, limit=CHART_LIMIT):
                ids[store_id] = None
        except AdapterError as exc:
            # Endpoint RSS này là đời cũ; Apple bỏ nó thì search vẫn chạy.
            logger.warning(
                "app store: bảng xếp hạng hỏng",
                extra={"feed": feed, "error": repr(exc)},
            )

    found: dict[str, Game] = {
        game.external_ids.app_store: game
        for game in await adapter.details(list(ids))
        if game.external_ids.app_store is not None
    }
    logger.info("app store: xong bảng xếp hạng", extra={"apps": len(ids), "games": len(found)})

    for term in seed_terms():
        try:
            for game in await adapter.search(term):
                if game.external_ids.app_store is not None:
                    found.setdefault(game.external_ids.app_store, game)
        except AdapterError as exc:
            logger.warning("app store: tìm hỏng", extra={"term": term, "error": repr(exc)})

    entities = list(found.values())
    game_ids = list(found)
    logger.info("app store: xong bước tìm", extra={"games": len(game_ids)})

    international = await adapter.international_names(game_ids)
    entities = [
        with_international_name(game, international.get(game.external_ids.app_store or ""))
        for game in entities
    ]

    tally = await _store_all(db, entities, key="app_store")
    await _reindex(ctx, since=started)
    logger.info("app store: xong", extra=dict(tally))
    return dict(tally)


async def _titles_to_probe(db: Db, limit: int, *, now: dt.datetime) -> list[tuple[Any, str]]:
    """`(game_id, tên)` của game iOS chưa biết bản Google Play và chưa dò gần đây.

    Đây là cầu nối giữa hai job: game vào catalog từ App Store, job Play lấy
    chính cái tên đó đi tìm bản Android, rồi `store_game` ghép hai bản lại.

    Bỏ qua tên đã dò trong `PLAY_RECHECK`: phần lớn game iOS không có bản Play
    trùng tên, và không có sổ thì chúng nằm mãi ở đầu danh sách, lượt nào cũng
    dò lại đúng 240 giây đầu.
    """
    recent = [
        doc["_id"]
        async for doc in db[PLAY_PROBES].find(
            {"probed_at": {"$gt": now - PLAY_RECHECK}}, {"_id": 1}
        )
    ]
    cursor = (
        games(db)
        .find(
            {"external_ids.google_play": None, "platforms": "ios", "_id": {"$nin": recent}},
            {"titles.primary": 1},
        )
        .limit(limit)
    )
    return [
        (doc["_id"], title)
        async for doc in cursor
        if (title := (doc.get("titles") or {}).get("primary"))
    ]


def _play_adapter(clients: Any) -> GooglePlayAdapter:
    """Tách riêng để test thay được bằng adapter giả."""
    return GooglePlayAdapter(
        AdapterConfig(limiter=RedisTokenBucket(clients.redis, "google_play", PLAY_RATE))
    )


async def sync_google_play(
    ctx: dict[str, Any],
    *,
    budget: float = PLAY_RUN_BUDGET,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, int]:
    """Tìm game trên Play theo từ khoá tiếng Việt + theo tên game iOS đã có.

    Chạy **từng phần**: hết `budget` giây thì dừng nhận việc, phần còn lại để
    lượt sau. Hai sổ ở Mongo (`play_apps`, `play_probes`) nhớ cái gì đã làm để
    lượt sau đi tiếp chứ không làm lại từ đầu.
    """
    clients = ctx["clients"]
    db: Db = clients.db
    started = dt.datetime.now(dt.UTC)
    deadline = clock() + budget
    adapter = _play_adapter(clients)
    tally = Tally()
    # Play trả 429 thì dừng cả lượt, không gọi tiếp: bị chặn theo IP là mất
    # luôn nguồn. Adapter đã chờ và thử lại trước khi ném lỗi này ra.
    bi_chan = False

    def het_luot() -> bool:
        return bi_chan or clock() >= deadline

    async def lay_va_ghi(app_ids: list[str]) -> bool:
        """Lấy chi tiết rồi GHI NGAY từng app — bị cắt ở đâu thì phần đã lấy
        vẫn còn. Trả về True nếu đã xử lý HẾT danh sách."""
        nonlocal bi_chan
        recent = {
            doc["_id"]
            async for doc in db[PLAY_APPS].find(
                {"_id": {"$in": app_ids}, "checked_at": {"$gt": started - PLAY_RECHECK}}, {"_id": 1}
            )
        }
        for app_id in app_ids:
            if app_id in recent:
                continue
            if het_luot():
                return False
            try:
                game = await adapter.detail(app_id)
            except RateLimitedError:
                bi_chan = True
                return False
            except AdapterError as exc:
                logger.warning(
                    "play: lấy chi tiết hỏng", extra={"app_id": app_id, "error": repr(exc)}
                )
                continue
            await db[PLAY_APPS].update_one(
                {"_id": app_id},
                {"$set": {"checked_at": dt.datetime.now(dt.UTC), "is_game": game is not None}},
                upsert=True,
            )
            if game is None:
                tally.add("not_game")
                continue
            try:
                tally.add(await store_game(db, game, key="google_play"))
            except Exception as exc:
                # Một app dị dạng không được chặn các app còn lại.
                tally.add("failed")
                logger.warning(
                    "không ghi được game mobile",
                    extra={"slug": game.slug, "key": "google_play", "error": repr(exc)},
                )
        return True

    async def ghi_so(khoa: Any) -> None:
        await db[PLAY_PROBES].update_one(
            {"_id": khoa}, {"$set": {"probed_at": dt.datetime.now(dt.UTC)}}, upsert=True
        )

    async def tim(query: str) -> list[str]:
        nonlocal bi_chan
        try:
            return await adapter.search_games(query, limit=SEARCH_HITS)
        except RateLimitedError:
            bi_chan = True
            return []
        except AdapterError as exc:
            # Một từ khoá hỏng không đáng để mất cả lượt chạy.
            logger.warning("play: tìm hỏng", extra={"query": query, "error": repr(exc)})
            return []

    # Từ khoá seed cũng vào sổ: đo ngày 2026-09-26, lượt đầu tiêu hết 240 giây
    # cho 28 từ khoá và chưa dò được tên iOS nào. Không có sổ thì lượt nào cũng
    # tìm lại 28 từ khoá (~84 giây ở 1 request/3 giây) trước khi tới phần dò.
    moc_seed = started - SEED_RECHECK
    da_tim_seed = {
        doc["_id"]
        async for doc in db[PLAY_PROBES].find(
            {"_id": {"$regex": "^term:"}, "probed_at": {"$gt": moc_seed}}, {"_id": 1}
        )
    }
    for term in seed_terms():
        if het_luot():
            break
        if f"term:{term}" in da_tim_seed:
            continue
        hits = await tim(term)
        # Chỉ ghi sổ khi đã xử lý TRỌN: bị cắt giữa chừng mà ghi thì các app
        # chưa lấy của từ khoá này mất tới lần dò sau.
        if not bi_chan and await lay_va_ghi(hits):
            await ghi_so(f"term:{term}")

    for game_id, title in await _titles_to_probe(db, CROSS_STORE_LIMIT, now=started):
        if het_luot():
            break
        hits = await tim(title)
        if bi_chan:
            break
        if await lay_va_ghi(hits):
            await ghi_so(game_id)
            tally.add("probed")

    if bi_chan:
        tally.add("rate_limited")
        logger.warning("play: bị 429, dừng lượt này", extra=dict(tally))
    elif clock() >= deadline:
        tally.add("budget_hit")
    await _reindex(ctx, since=started)
    logger.info("play: xong", extra=dict(tally))
    return dict(tally)


async def _reindex(ctx: dict[str, Any], *, since: dt.datetime) -> None:
    """Đẩy phần vừa đổi sang Meilisearch.

    Delta chứ không phải toàn bộ: `content_hash` bảo đảm `updated_at` chỉ nhảy
    ở entity thật sự đổi, nên chạy lại job mà không có gì mới thì đây là một
    lần quét rỗng.
    """
    index = ctx.get("meili")
    if index is None:
        return
    count = await reindex(ctx["clients"].db, index, since=since)
    logger.info("đã đẩy sang meilisearch", extra={"documents": count})
