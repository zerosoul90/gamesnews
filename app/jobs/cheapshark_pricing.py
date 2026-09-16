"""Job lấy giá nhiều store từ CheapShark.

`CheapSharkAdapter` có trong repo từ trước nhưng **không job nào gọi**, và bản cũ
của nó còn thiếu User-Agent nên mọi lời gọi đều sẽ `400`. Tới lượt này
`price_current` chỉ có `steam` và `epic`, nên bảng giá trên trang game gần như
luôn một dòng.

Hai bước, vì CheapShark chỉ cho tra lô ở một trong hai:

1. **Giải `gameID`** cho game có `steam_appid` mà chưa có `external_ids.cheapshark_id`.
   Một request một game — `steamAppID` không nhận danh sách. Lưu lại để không
   bao giờ phải hỏi lần hai.
2. **Đọc giá** cho game đã có `cheapshark_id`, theo lô 25 (trần thật của `ids`).

Nhờ bước 1 lưu kết quả, chi phí giảm dần: lượt đầu tốn một request mỗi game mới,
còn việc làm mới giá thì 25 game một request.

**Hai lỗi sửa 2026-09-16, cùng phát hiện từ một dòng log thật.** Lượt 15:42 UTC
trả `refreshed: 125, failed: 3` — ba lô cuối ăn 429.

1. *Không có cổng nhịp.* Job bắn ~33 request liền mạch, mà CheapShark chặn ở
   ~36/60 giây (xem `RATE_LIMIT`). Nay cả job đi qua một `RedisTokenBucket`.
2. *Hàng đợi không quay.* `_refresh_prices` sắp xếp theo `_id` rồi cắt 200, nên
   nó lấy đúng 200 game có `_id` nhỏ nhất, mỗi 30 phút, mãi mãi — 992/1.192 game
   không bao giờ được làm mới giá. Nay sắp xếp theo `intl_checked_at`.

Hai lỗi cộng lại: chỉ ~125/1.192 game (10%) thực sự có giá được cập nhật, và
`failed: 3` là tín hiệu duy nhất lộ ra — nó trông như lỗi mạng lẻ tẻ, không như
một phần ba kho hàng đứng im.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from app.adapters.base import AdapterError, RateLimitedError, RedisTokenBucket
from app.adapters.cheapshark.adapter import IDS_BATCH, RATE_LIMIT, CheapSharkAdapter
from app.services.intl_prices import save_intl_prices

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

SOURCE = "cheapshark"

# Mốc xoay vòng, đặt trên `games` chứ không đọc `price_intl.checked_at`. Cùng
# idiom với `games.price_checked_at` của job giá Steam, và vì lý do thực tế: game
# CHƯA đọc lần nào không có document `price_intl` nào cả, nên sắp xếp bên đó thì
# đúng những game cần nhất lại không bao giờ xuất hiện.
CHECKED_AT = "intl_checked_at"

INDEXES: list[IndexModel] = [
    # Truy vấn duy nhất của `_refresh_prices`: game có `cheapshark_id`, cũ nhất
    # trước. Thiếu index này thì mỗi lượt là một collection scan trên `games`.
    IndexModel(
        [("external_ids.cheapshark_id", ASCENDING), (CHECKED_AT, ASCENDING)],
        name="cheapshark_checked",
    ),
]

# Số game mỗi lượt được phép giải `gameID` mới. Mỗi cái là một request, nên đây là
# phần đắt; để thấp và gặm dần vì nó chỉ phải làm một lần cho mỗi game.
MAX_RESOLVE = 20

# Số game mỗi lượt được làm mới giá. 200 game = 8 request nhờ lô 25.
#
# Đây KHÔNG còn là "200 game đầu tiên theo `_id`" như trước. Với 1.192 game đã có
# `cheapshark_id` (đo 2026-09-16), cách cũ nghĩa là 992 game — 83% — không bao giờ
# lọt vào lượt nào và giá của chúng đóng băng vĩnh viễn ở lần ghi đầu. Nay sắp xếp
# theo `CHECKED_AT` nên 200 là một CỬA SỔ TRƯỢT: cả kho quay hết một vòng sau
# 1192/200 ≈ 6 lượt, tức ~3 giờ ở nhịp cron 30 phút.
MAX_REFRESH = 200

# Sàn mà phần GIẢI ID không được phạm vào, chừa cho phần LÀM MỚI GIÁ:
#
#   1 (`/stores`) + 8 (làm mới, 200/25) = 9
#
# Đối chiếu với `RATE_LIMIT.capacity = 30`: phần giải id còn dùng được 30 - 9 =
# 21, đủ cho `MAX_RESOLVE = 20`. Tức lượt bình thường tiêu 29/30 token và không
# phần nào phải chờ.
#
# Vượt ngân sách không làm hỏng gì: bucket cho chờ, quá `max_wait_seconds` thì ném
# `RateLimitedError` và job dừng lượt sạch sẽ. Con số này chỉ để lượt BÌNH THƯỜNG
# không bao giờ phải đi tới đó.
REFRESH_RESERVE = 9


async def sync_cheapshark_prices(ctx: dict[str, Any]) -> dict[str, int]:
    """Giải `gameID` cho game mới, rồi làm mới giá cho game đã biết.

    Giữ nguyên thứ tự cũ để game vừa được giải id có giá NGAY trong lượt này,
    không phải đợi lượt sau — nhịp cron là 30 phút, và một game mới không có
    bảng giá suốt nửa tiếng là thứ người dùng nhìn thấy.

    Nhưng thứ tự ấy có cái giá: hai phần dùng chung một hạn mức tính theo IP, nên
    phần chạy trước vét bucket trước. Với `MAX_RESOLVE` request, giải id gần như
    lấy sạch và làm mới giá chết đói mỗi lượt — cùng lớp starvation đã sửa cho
    `last_crawled_at` ở lượt 2, lần này giữa hai phần của CÙNG một job.

    Nên phần giải id đi qua một bucket có `reserve`: nó tự nguyện không phạm vào
    `REFRESH_RESERVE` token cuối, còn phần làm mới giá thì được dùng tới token
    cuối cùng. Đúng công dụng mà `RedisTokenBucket.reserve` được viết ra.
    """
    clients = ctx["clients"]
    db: Db = clients.db
    await ensure_indexes(db)

    # Cùng một KEY bucket cho cả hai — CheapShark chặn theo IP, tách key ra là mỗi
    # phần lại tưởng mình còn nguyên hạn mức. Khác nhau chỉ ở `reserve`, vốn là
    # thuộc tính của NGƯỜI GỌI chứ không của bucket.
    def _adapter(reserve: int) -> CheapSharkAdapter:
        return CheapSharkAdapter(
            clients.http,
            RedisTokenBucket(clients.redis, "cheapshark", RATE_LIMIT, reserve=reserve),
        )

    an_toan = _adapter(REFRESH_RESERVE)
    uu_tien = _adapter(0)

    tally = {"resolved": 0, "unresolved": 0, "refreshed": 0, "no_deals": 0, "failed": 0}

    try:
        # Bảng tên store đi bằng suất ưu tiên: nó nằm trong ngân sách của phần làm
        # mới giá (xem `REFRESH_RESERVE`), không phải của phần giải id.
        stores = await uu_tien.stores()
    except AdapterError:
        # Không có bảng tên store thì vẫn ghi được giá, chỉ là hiện "store 23".
        # Không đáng để bỏ cả lượt.
        stores = {}

    await _resolve_new_ids(db, an_toan, tally)
    await _refresh_prices(db, uu_tien, stores, tally)
    logger.info("cheapshark: xong lượt", extra=tally)
    return tally


async def ensure_indexes(db: Db) -> list[str]:
    return await db.games.create_indexes(INDEXES)


async def _danh_dau_da_doc(db: Db, game_ids: list[Any]) -> None:
    """Dập mốc xoay vòng cho một lô game.

    Tách ra thành hàm riêng vì nó được gọi từ CẢ nhánh thành công lẫn nhánh hỏng,
    và hai chỗ phải dập cùng một trường — quên một chỗ là lô đó kẹt lại đầu hàng
    đợi mãi mãi.
    """
    await db.games.update_many(
        {"_id": {"$in": game_ids}}, {"$set": {CHECKED_AT: dt.datetime.now(dt.UTC)}}
    )


async def _resolve_new_ids(db: Db, adapter: CheapSharkAdapter, tally: dict[str, int]) -> None:
    """Điền `external_ids.cheapshark_id` cho game chưa có.

    Join bằng `steam_appid`, KHÔNG khớp theo tên: CheapShark trả sẵn `steamAppID`
    trong payload, nên đây là join chính xác chứ không phải phỏng đoán. Job Epic
    phải khớp theo tên chỉ vì payload của Epic không có ID Steam nào.
    """
    cursor = (
        db.games.find(
            {
                "external_ids.steam_appid": {"$ne": None},
                "external_ids.cheapshark_id": None,
            },
            {"external_ids.steam_appid": 1},
        )
        .sort("_id", 1)
        .limit(MAX_RESOLVE)
    )

    async for doc in cursor:
        appid = (doc.get("external_ids") or {}).get("steam_appid")
        if appid is None:
            continue
        try:
            game_id = await adapter.game_id_for_steam_appid(int(appid))
        except RateLimitedError as exc:
            # Dừng cả vòng, không chỉ game này: bucket đã cạn thì mọi game còn
            # lại trong lô cũng cạn y như vậy, và duyệt tiếp chỉ để đếm thêm
            # `failed` cho những lời gọi không bao giờ được gửi đi.
            logger.info(
                "bucket cheapshark cạn, dừng vòng giải id tại đây",
                extra={"da_giai": tally["resolved"], "error": str(exc)},
            )
            break
        except AdapterError:
            # Không ghi gì vào `cheapshark_id`: `None` vẫn nghĩa là "chưa hỏi",
            # nên lượt sau hỏi lại. Khác hẳn nhánh `game_id is None` bên dưới —
            # ở đó CheapShark đã TRẢ LỜI là không có.
            tally["failed"] += 1
            continue

        if game_id is None:
            # CheapShark không biết app này. Ghi chuỗi rỗng để lượt sau không hỏi
            # lại mãi — `None` nghĩa là "chưa hỏi", `""` nghĩa là "hỏi rồi,
            # không có". Thiếu phân biệt đó thì mỗi lượt lại tốn một request cho
            # đúng những game không bao giờ có kết quả.
            await db.games.update_one(
                {"_id": doc["_id"]}, {"$set": {"external_ids.cheapshark_id": ""}}
            )
            tally["unresolved"] += 1
            continue

        await db.games.update_one(
            {"_id": doc["_id"]}, {"$set": {"external_ids.cheapshark_id": game_id}}
        )
        tally["resolved"] += 1


async def _refresh_prices(
    db: Db, adapter: CheapSharkAdapter, stores: dict[str, str], tally: dict[str, int]
) -> None:
    """Đọc giá từng store cho game đã có `cheapshark_id`, LÂU CHƯA ĐỌC NHẤT trước.

    Game chưa đọc lần nào không có trường `CHECKED_AT`, và Mongo xếp document
    thiếu trường lên TRƯỚC mọi giá trị ngày khi sắp tăng dần — nên chúng tự động
    được ưu tiên mà không cần nhánh `$or` riêng như `price_tier.due_for_check`.
    Khác biệt là ở đó có điều kiện "tới hạn" (`$lt` một mốc), còn ở đây không:
    mỗi lượt cứ lấy 200 cái cũ nhất, nên hàng đợi luôn quay chứ không bao giờ
    rỗng.
    """
    cursor = (
        db.games.find(
            # `{"$nin": [None, ""]}`: bỏ cả game chưa hỏi và game đã hỏi mà
            # CheapShark không có.
            {"external_ids.cheapshark_id": {"$nin": [None, ""]}},
            {"external_ids.cheapshark_id": 1},
        )
        .sort([(CHECKED_AT, ASCENDING)])
        .limit(MAX_REFRESH)
    )

    by_cheapshark_id: dict[str, Any] = {}
    async for doc in cursor:
        cheapshark_id = str((doc.get("external_ids") or {}).get("cheapshark_id") or "")
        if cheapshark_id:
            by_cheapshark_id[cheapshark_id] = doc["_id"]

    ids = list(by_cheapshark_id)
    for start in range(0, len(ids), IDS_BATCH):
        chunk = ids[start : start + IDS_BATCH]
        chunk_game_ids = [by_cheapshark_id[cid] for cid in chunk]
        try:
            payloads = await adapter.prices_for_game_ids(chunk)
        except RateLimitedError as exc:
            # Bucket cạn -> DỪNG lượt, và KHÔNG dập mốc: lô này chưa hề được thử,
            # nên lượt sau phải lấy lại đúng nó. Dập mốc ở đây là đẩy 25 game
            # xuống cuối hàng đợi vì một lời gọi chưa từng xảy ra.
            logger.info(
                "bucket cheapshark cạn, dừng lượt làm mới tại đây",
                extra={"da_lam_moi": tally["refreshed"], "error": str(exc)},
            )
            break
        except AdapterError:
            # Đã gọi thật và hỏng (429 từ chính CheapShark, 5xx, JSON rác). Ở đây
            # thì PHẢI dập mốc: không dập thì đúng lô hỏng ấy nằm mãi ở đầu hàng
            # đợi và không game nào khác được đọc — cùng bài học với
            # `price_checked_at` của job giá Steam.
            await _danh_dau_da_doc(db, chunk_game_ids)
            tally["failed"] += 1
            continue

        await _danh_dau_da_doc(db, chunk_game_ids)
        for cheapshark_id in chunk:
            payload = payloads.get(cheapshark_id)
            if payload is None:
                # Không store nào bán, hoặc CheapShark bỏ id này khỏi response.
                tally["no_deals"] += 1
                continue

            await save_intl_prices(
                db,
                by_cheapshark_id[cheapshark_id],
                SOURCE,
                {**payload, "deals": _with_store_names(payload["deals"], stores)},
            )
            tally["refreshed"] += 1


def _with_store_names(deals: list[dict[str, Any]], stores: dict[str, str]) -> list[dict[str, Any]]:
    """Gắn tên store vào từng dòng giá.

    Gắn lúc GHI, không lúc đọc: bảng `/stores` là một request riêng, và trang game
    không nên phải gọi thêm một lượt nữa chỉ để dịch "23" thành "GreenManGaming".
    Tên store đổi rất chậm, nên ảnh chụp tại thời điểm ghi là đủ.
    """
    return [
        {**deal, "store": stores.get(deal["store_id"]) or f"store {deal['store_id']}"}
        for deal in deals
    ]
