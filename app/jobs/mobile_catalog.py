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
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.app_store.adapter import (
    CHART_LIMIT,
    AppStoreAdapter,
    Feed,
    with_international_name,
)
from app.adapters.app_store.adapter import RATE_LIMIT as APP_STORE_RATE
from app.adapters.base import AdapterConfig, AdapterError, RedisTokenBucket
from app.adapters.google_play.adapter import RATE_LIMIT as PLAY_RATE
from app.adapters.google_play.adapter import GooglePlayAdapter
from app.models.game import Game
from app.services.catalog import games
from app.services.mobile_catalog import StoreOutcome, store_game
from app.services.search_index import reindex

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Bảng xếp hạng game của gian hàng VN. Chỉ endpoint RSS đời cũ lọc được theo
# thể loại — xem adapter. Đây là nguồn phụ; nguồn chính là search theo từ khoá.
FEEDS: tuple[Feed, ...] = ("top-free", "top-paid", "top-grossing")

# Mỗi từ khoá lấy 30 kết quả. Con số nhỏ là có chủ ý: kết quả càng sâu càng
# loãng, mà mỗi app còn tốn thêm hai request nữa ở bước lấy chi tiết.
SEARCH_HITS = 30

# Trần số game iOS đem đi dò trên Play mỗi lượt. Mỗi cái tốn một lần search +
# hai lần lấy chi tiết, ở mức 1 request/giây thì đây đã là khoảng 20 phút.
CROSS_STORE_LIMIT = 300

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


async def _titles_to_probe(db: Db, limit: int) -> list[str]:
    """Tên game đã có trong catalog nhưng chưa biết bản Google Play.

    Đây là cầu nối giữa hai job: game vào catalog từ App Store, job Play lấy
    chính cái tên đó đi tìm bản Android, rồi `store_game` ghép hai bản lại.
    """
    cursor = (
        games(db)
        .find(
            {"external_ids.google_play": None, "platforms": "ios"},
            {"titles.primary": 1},
        )
        .limit(limit)
    )
    return [title async for doc in cursor if (title := (doc.get("titles") or {}).get("primary"))]


async def sync_google_play(ctx: dict[str, Any]) -> dict[str, int]:
    """Tìm game trên Play theo từ khoá tiếng Việt + theo tên game iOS đã có."""
    clients = ctx["clients"]
    db: Db = clients.db
    started = dt.datetime.now(dt.UTC)

    adapter = GooglePlayAdapter(
        AdapterConfig(limiter=RedisTokenBucket(clients.redis, "google_play", PLAY_RATE))
    )

    queries = [*seed_terms(), *await _titles_to_probe(db, CROSS_STORE_LIMIT)]
    app_ids: set[str] = set()
    for query in queries:
        try:
            app_ids.update(await adapter.search_games(query, limit=SEARCH_HITS))
        except AdapterError as exc:
            # Một từ khoá hỏng không đáng để mất cả lượt chạy.
            logger.warning("play: tìm hỏng", extra={"query": query, "error": repr(exc)})

    logger.info("play: xong bước tìm", extra={"queries": len(queries), "apps": len(app_ids)})

    entities: list[Game] = []
    for app_id in sorted(app_ids):
        try:
            if (game := await adapter.detail(app_id)) is not None:
                entities.append(game)
        except AdapterError as exc:
            logger.warning("play: lấy chi tiết hỏng", extra={"app_id": app_id, "error": repr(exc)})

    tally = await _store_all(db, entities, key="google_play")
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
