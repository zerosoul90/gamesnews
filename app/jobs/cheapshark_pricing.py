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
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.base import AdapterError
from app.adapters.cheapshark.adapter import IDS_BATCH, CheapSharkAdapter
from app.services.intl_prices import save_intl_prices

Db = AsyncIOMotorDatabase[dict[str, Any]]

SOURCE = "cheapshark"

# Số game mỗi lượt được phép giải `gameID` mới. Mỗi cái là một request, nên đây là
# phần đắt; để thấp và gặm dần vì nó chỉ phải làm một lần cho mỗi game.
MAX_RESOLVE = 25

# Số game mỗi lượt được làm mới giá. 200 game = 8 request nhờ lô 25.
MAX_REFRESH = 200


async def sync_cheapshark_prices(ctx: dict[str, Any]) -> dict[str, int]:
    """Giải `gameID` cho game mới, rồi làm mới giá cho game đã biết."""
    clients = ctx["clients"]
    db: Db = clients.db
    adapter = CheapSharkAdapter(clients.http)

    tally = {"resolved": 0, "unresolved": 0, "refreshed": 0, "no_deals": 0, "failed": 0}

    try:
        stores = await adapter.stores()
    except AdapterError:
        # Không có bảng tên store thì vẫn ghi được giá, chỉ là hiện "store 23".
        # Không đáng để bỏ cả lượt.
        stores = {}

    await _resolve_new_ids(db, adapter, tally)
    await _refresh_prices(db, adapter, stores, tally)
    return tally


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
        except AdapterError:
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
    """Đọc giá từng store cho game đã có `cheapshark_id`."""
    cursor = (
        db.games.find(
            # `{"$nin": [None, ""]}`: bỏ cả game chưa hỏi và game đã hỏi mà
            # CheapShark không có.
            {"external_ids.cheapshark_id": {"$nin": [None, ""]}},
            {"external_ids.cheapshark_id": 1},
        )
        .sort("_id", 1)
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
        try:
            payloads = await adapter.prices_for_game_ids(chunk)
        except AdapterError:
            tally["failed"] += 1
            continue

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
