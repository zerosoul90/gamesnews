import datetime as dt
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import InsertOne, UpdateOne

from app.models.game import PyObjectId
from app.models.price import PriceCurrent, PriceHistory
from app.services.notification import NotificationPayload, process_notification


async def record_prices(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    prices_data: list[PriceCurrent],
) -> dict[str, int]:
    """Ghi nhận giá của một lô game.

    Cập nhật `price_current` và thêm vào `price_history` NẾU giá thay đổi.
    Trả về số lượng giá được cập nhật và số lượng thay đổi giá (history).
    """
    if not prices_data:
        return {"updated": 0, "history_added": 0}

    now = dt.datetime.now(dt.UTC).isoformat()

    # Lấy giá hiện tại của toàn bộ lô để tính delta và lowest_ever
    conditions = [{"game_id": p.game_id, "store": p.store, "region": p.region} for p in prices_data]
    current_cursor = db.price_current.find({"$or": conditions})
    current_map = {}
    async for doc in current_cursor:
        key = (doc["game_id"], doc["store"], doc["region"])
        current_map[key] = doc

    current_ops = []
    history_ops = []

    # Danh sách các game giảm giá để check alert
    dropped_prices: list[PriceCurrent] = []

    for new_price in prices_data:
        key = (new_price.game_id, new_price.store, new_price.region)
        old_price = current_map.get(key)

        price_changed = True
        lowest_ever = new_price.price_final
        lowest_ever_date = now

        if old_price:
            prev_final = old_price.get("price_final")
            prev_lowest = old_price.get("lowest_ever")

            # Chỉ ghi lịch sử khi giá (hoặc %) thực sự đổi
            if (
                prev_final == new_price.price_final
                and old_price.get("discount_percent") == new_price.discount_percent
            ):
                price_changed = False

            # Tính lại lowest_ever
            if prev_lowest is not None and prev_lowest <= new_price.price_final:
                lowest_ever = prev_lowest
                lowest_ever_date = old_price.get("lowest_ever_date") or now

        new_price.lowest_ever = lowest_ever
        new_price.lowest_ever_date = lowest_ever_date
        new_price.is_historical_low = (
            new_price.price_final <= lowest_ever and new_price.price_final > 0
        )
        new_price.checked_at = now

        current_ops.append(
            UpdateOne(
                {
                    "game_id": new_price.game_id,
                    "store": new_price.store,
                    "region": new_price.region,
                },
                {"$set": new_price.to_mongo()},
                upsert=True,
            )
        )

        if price_changed:
            history = PriceHistory(
                game_id=new_price.game_id,
                store=new_price.store,
                region=new_price.region,
                price_final=new_price.price_final,
                discount_percent=new_price.discount_percent,
                changed_at=now,
            )
            history_ops.append(InsertOne(history.to_mongo()))

            # Nếu giá giảm, đưa vào danh sách kiểm tra cảnh báo
            if old_price and new_price.price_final < old_price.get("price_final", float("inf")):
                dropped_prices.append(new_price)
            elif not old_price and new_price.discount_percent > 0:
                # Game mới hoàn toàn nhưng đang có giảm giá
                dropped_prices.append(new_price)

    if current_ops:
        await db.price_current.bulk_write(current_ops)
    if history_ops:
        await db.price_history.bulk_write(history_ops)

    # Trigger Push Notification / Cảnh báo giá
    if dropped_prices:
        await _check_price_alerts_batch(db, dropped_prices)

    return {"updated": len(current_ops), "history_added": len(history_ops)}


async def _check_price_alerts_batch(
    db: AsyncIOMotorDatabase[dict[str, Any]], dropped_prices: list[PriceCurrent]
) -> None:
    """Quét các price_alert khớp với lô giá vừa giảm."""
    game_ids = [p.game_id for p in dropped_prices]
    price_map = {p.game_id: p for p in dropped_prices}

    # Tìm tất cả alert của các game này
    cursor = db.price_alerts.find({"game_id": {"$in": game_ids}})

    async for alert in cursor:
        game_id = alert["game_id"]
        price = price_map[game_id]

        condition = alert.get("condition")
        value = alert.get("value")
        triggered = False

        if (
            (condition == "below_price" and value is not None and price.price_final <= value)
            or (
                condition == "discount_pct"
                and value is not None
                and price.discount_percent >= value
            )
            or (condition == "historical_low" and price.is_historical_low)
        ):
            triggered = True

        if triggered:
            payload = NotificationPayload(
                user_id=alert["user_id"],
                type="price_alert",
                title="Cảnh báo giảm giá!",
                body=(
                    f"Game bạn theo dõi đã giảm xuống còn {price.price_final} "
                    f"{price.currency} (-{price.discount_percent}%)"
                ),
                data={"game_id": str(game_id), "store": price.store},
            )
            # Await thẳng, không create_task. Task không được giữ tham chiếu
            # thì bộ thu gom rác có quyền dọn nó giữa chừng và thông báo biến
            # mất không dấu vết. Số alert mỗi lần giá đổi vốn nhỏ, nên cái giá
            # của việc await là không đáng kể so với việc mất thông báo.
            await process_notification(db, payload)

            # Cập nhật triggered_at
            await db.price_alerts.update_one(
                {"_id": alert["_id"]},
                {"$set": {"triggered_at": dt.datetime.now(dt.UTC).isoformat()}},
            )


async def mark_region_locked(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    game_ids: list[PyObjectId],
) -> int:
    """Đánh dấu các game khóa vùng VN."""
    if not game_ids:
        return 0
    result = await db.games.update_many(
        {"_id": {"$in": game_ids}}, {"$set": {"region_locked_vn": True}}
    )
    return result.modified_count
