"""Hai job xây catalog PC từ Steam — thay cho job IGDB của `PHASE-1.md` mục 1.

Tách làm hai vì chúng có nhịp hoàn toàn khác nhau:

- `sync_steam_app_list` — vài request, xong trong một phút, chạy mỗi ngày một
  lần là đủ. Nó chỉ ghi vào sổ công việc `steam_apps`.
- `sync_steam_details` — nghẽn ở ~200 request/5 phút mỗi IP, tức ~57.600
  lượt/ngày cho gần 185.000 app. Lượt đầu vì vậy mất **vài ngày**. Job này chạy
  từng lô, nối tiếp được sau khi worker restart, và không bao giờ chạy "cho tới
  hết" trong một lần.

Gộp hai việc vào một job thì mỗi lần muốn làm mới danh sách lại phải chờ cả
đợt bồi chi tiết, còn worker restart giữa chừng là mất dấu.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.adapters.base import AdapterConfig, AdapterError, RedisTokenBucket
from app.adapters.steam.adapter import (
    APP_LIST_RATE_LIMIT,
    DETAILS_RATE_LIMIT,
    SteamCatalogAdapter,
    parent_appid,
    to_game,
)
from app.core.config import get_settings
from app.models.game import Game
from app.services import steam_queue
from app.services.catalog import find_game_by_external_id
from app.services.ingest import store_game
from app.services.search_index import reindex

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Một lô bồi chi tiết. 200 là đúng trần 5 phút của Steam, nên một lượt job tiêu
# hết bucket rồi nhường chỗ, thay vì ngồi chờ trong khi giữ kết nối.
DETAILS_BATCH = 200

# Số token job này tự chừa lại trong bucket `steam_appdetails` dùng chung.
#
# `docs/CLAUDE.md`: "không được để một job làm cạn quota của job khác". Job bồi
# chi tiết gọi appdetails **một request mỗi appid**, tuần tự tới 200 lần một lượt,
# nên nó là job duy nhất có thể vét sạch bucket — ba job kia đều nhỏ hoặc gộp lô.
#
# 25 được chọn theo nhu cầu lớn nhất của một lượt chạy mà người dùng thấy độ trễ
# ngay: `sync_steam_prices` gộp 50 appid mỗi request nên tối đa 20 request, cộng
# job Epic 1 request.
#
# Nói cho đúng phạm vi: sàn chỉ bảo đảm bucket KHÔNG bị vét về 0, nó không phân
# xử giữa các job còn lại. `sync_steam_reviews` cũng không đặt sàn nên về nguyên
# tắc nó có thể lấy trước phần đó. Thực tế lịch đã tách chúng ra (giá ở phút
# :00/:15/:30/:45, review ở :08/:38, catalog ở :05/:20/:35/:50) và refill
# 0,667 token/s tự tạo thêm khoảng cách, nên cái sàn này là mạng an toàn cho lúc
# lịch bị xô lệch — không phải cơ chế ưu tiên.
#
# Giá phải trả: mỗi lượt bồi tối đa 175 thay vì 200 request, tức 700/giờ thay vì
# 800 — chậm khoảng 12% việc bồi 185k app.
DETAILS_RESERVE = 25


def _adapter(ctx: dict[str, Any], *, keyed: bool) -> SteamCatalogAdapter:
    clients = ctx["clients"]
    settings = get_settings()
    # Hai bucket riêng: job catalog không được ăn mất quota appdetails mà
    # Phase 2 sẽ cần cho việc lấy giá.
    limit = APP_LIST_RATE_LIMIT if keyed else DETAILS_RATE_LIMIT
    name = "steam_applist" if keyed else "steam_appdetails"
    # Chỉ bucket appdetails cần sàn: `steam_applist` không ai dùng chung.
    reserve = 0 if keyed else DETAILS_RESERVE
    return SteamCatalogAdapter(
        AdapterConfig(limiter=RedisTokenBucket(clients.redis, name, limit, reserve=reserve)),
        clients.http,
        api_key=settings.steam_api_key.get_secret_value(),
    )


async def sync_steam_app_list(ctx: dict[str, Any]) -> dict[str, int]:
    """Lật hết danh sách game của Steam vào sổ công việc `steam_apps`."""
    db: Db = ctx["clients"].db
    await steam_queue.ensure_indexes(db)

    adapter = _adapter(ctx, keyed=True)
    cursor: int | None = 0
    seen = 0
    added = 0
    pages = 0

    while cursor is not None:
        apps, cursor = await adapter.app_list_page(cursor)
        if not apps:
            break
        added += await steam_queue.enqueue(db, [(app.appid, app.name) for app in apps])
        seen += len(apps)
        pages += 1

    result = {"pages": pages, "seen": seen, "added": added}
    logger.info("steam: xong danh sách app", extra={**result, **await steam_queue.counts(db)})
    return result


async def sync_steam_details(ctx: dict[str, Any], batch: int = DETAILS_BATCH) -> dict[str, int]:
    """Bồi chi tiết cho một lô app đang chờ, rồi ghi entity vào `games`."""
    db: Db = ctx["clients"].db
    started = dt.datetime.now(dt.UTC)
    adapter = _adapter(ctx, keyed=False)

    appids = await steam_queue.take_pending(db, batch)
    tally = {"done": 0, "skipped": 0, "missing": 0, "failed": 0, "conflict": 0}

    for appid in appids:
        try:
            data = await adapter.details(appid)
        except AdapterError as exc:
            # Trả về `pending` để lần sau thử lại. Lỗi mạng không phải bằng chứng
            # app này có vấn đề — nhưng từ khi hàng đợi giành việc thì không trả
            # lại là app treo ở `taken` tới hết lease.
            await steam_queue.release(db, appid)
            tally["failed"] += 1
            logger.warning("steam: lấy chi tiết hỏng", extra={"appid": appid, "error": repr(exc)})
            continue

        if data is None:
            # success=false — app đã gỡ, hoặc không bán ở VN. Không phải lỗi.
            await steam_queue.mark(db, appid, "missing")
            tally["missing"] += 1
            continue

        try:
            game = to_game(data)
        except AdapterError as exc:
            await steam_queue.mark(db, appid, "skipped", reason=str(exc)[:200])
            tally["failed"] += 1
            continue

        if game is None:
            # Nhạc nền, phần mềm dựng phim, phần cứng... Bỏ qua là đúng.
            await steam_queue.mark(db, appid, "skipped", reason=str(data.get("type")))
            tally["skipped"] += 1
            continue

        game = await _with_parent(db, game, data)
        try:
            await store_game(db, game, key="steam_appid")
        except DuplicateKeyError as exc:
            # Một app không được giết cả lô 200 app còn lại. Trước lượt này lỗi
            # này thoát ra khỏi job, nên việc bồi 185k app dừng hẳn tại đúng app
            # đó mỗi lần chạy.
            #
            # Nguyên nhân đã biết là hai lượt chạy chồng nhau, và `take_pending`
            # giành việc nên nhánh này lẽ ra không còn với tới được. Nếu nó vẫn
            # hiện trong log thì là chuyện khác, chưa biết — nên ghi `reason` vào
            # hàng đợi để tra được sau, chứ không chỉ ghi log rồi thả ra.
            #
            # Đánh `skipped` chứ không trả về `pending`: nếu đây là lỗi dữ liệu
            # bền thì trả lại là vòng lặp retry vô tận, đốt quota Steam mà không
            # bao giờ xong.
            await steam_queue.mark(db, appid, "skipped", reason=f"duplicate_key: {exc!s:.180}")
            tally["conflict"] += 1
            logger.warning(
                "steam: đụng khoá unique khi ghi entity",
                extra={"appid": appid, "slug": game.slug, "error": repr(exc)},
            )
            continue
        await steam_queue.mark(db, appid, "done")
        tally["done"] += 1

    await _reindex(ctx, since=started)
    logger.info("steam: xong một lô chi tiết", extra={"batch": len(appids), **tally})
    return tally


async def _with_parent(db: Db, game: Game, data: dict[str, Any]) -> Game:
    """Nối DLC về game cha nếu game cha đã có trong catalog.

    `PHASE-1.md` mục 2 bắt DLC phải trỏ `parent_game`. Game cha chưa được bồi
    chi tiết thì để trống — hàng đợi đi theo appid tăng dần nên game cha
    thường tới trước, còn trường hợp ngược lại thì lượt đồng bộ sau vá được.
    """
    appid = parent_appid(data)
    if appid is None:
        return game

    parent = await find_game_by_external_id(db, "steam_appid", appid)
    if parent is None:
        return game
    return game.model_copy(update={"parent_game": parent["_id"]})


async def _reindex(ctx: dict[str, Any], *, since: dt.datetime) -> None:
    index = ctx.get("meili")
    if index is None:
        return
    count = await reindex(ctx["clients"].db, index, since=since)
    logger.info("đã đẩy sang meilisearch", extra={"documents": count})
