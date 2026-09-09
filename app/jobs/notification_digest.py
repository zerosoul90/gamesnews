import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.notification import send_push_notification

logger = logging.getLogger(__name__)


async def send_notification_digest(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Job chạy hàng ngày.
    Gom các thông báo bị kẹt trong `notification_queue` thành một digest và gửi FCM.
    """
    db: AsyncIOMotorDatabase[dict[str, Any]] = ctx["clients"].db
    
    # 1. Tìm tất cả user có thông báo trong queue
    cursor = db.notification_queue.aggregate([
        {"$group": {
            "_id": "$user_id",
            "count": {"$sum": 1},
            "items": {"$push": {"title": "$title", "type": "$type"}}
        }}
    ])
    
    users_processed = 0
    notifications_sent = 0
    
    async for user_data in cursor:
        user_id = user_data["_id"]
        count = user_data["count"]
        items = user_data["items"]
        
        # Tạo nội dung digest
        title = f"Bản tin GameNews ({count} cập nhật)"
        body = f"Bạn có {count} thông báo mới, bao gồm: {items[0]['title']}"
        if count > 1:
            body += f" và {count - 1} tin khác."
            
        # Mock gửi FCM
        await send_push_notification(user_id, title, body, {"type": "digest"})
        notifications_sent += count
        users_processed += 1
        
    # Xoá queue sau khi gửi thành công
    if users_processed > 0:
        await db.notification_queue.delete_many({})
        
    logger.info("Hoàn thành Notification Digest", extra={"users": users_processed, "notifications": notifications_sent})
    return {"users_processed": users_processed, "notifications_sent": notifications_sent}
