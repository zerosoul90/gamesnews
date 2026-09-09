"""Client tới các kho dữ liệu, khởi tạo và đóng theo lifespan của FastAPI.

`PHASE-0.md` chỉ nêu client Motor. Redis và client HTTP dùng chung cho
Meilisearch/Qdrant cũng đặt ở đây vì chúng có cùng vòng đời: mở lúc app khởi
động, đóng lúc tắt. Tách ra file khác chỉ làm lifespan phải quản lý nhiều chỗ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.core.config import Settings


@dataclass(slots=True)
class Clients:
    mongo: AsyncIOMotorClient[dict[str, Any]]
    redis: Redis
    http: httpx.AsyncClient
    # Tầng 3 gắn entity (`services/embeddings.py`). Nó có vòng đời y hệt ba
    # client kia nên nằm cùng chỗ; `/health` vẫn ping Qdrant bằng `http` vì chỉ
    # cần biết cổng có trả lời không.
    qdrant: AsyncQdrantClient
    db_name: str

    @property
    def db(self) -> AsyncIOMotorDatabase[dict[str, Any]]:
        return self.mongo[self.db_name]


async def create_clients(settings: Settings) -> Clients:
    mongo: AsyncIOMotorClient[dict[str, Any]] = AsyncIOMotorClient(
        settings.mongo_uri,
        # Không để driver treo mãi khi Mongo chết; /health phải trả lời nhanh.
        serverSelectionTimeoutMS=int(settings.health_timeout_seconds * 1000),
        tz_aware=True,
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    http = httpx.AsyncClient(timeout=settings.health_timeout_seconds)
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        # Không dò phiên bản server lúc khởi tạo: client sẽ gọi mạng ngay trong
        # `create_clients` và cảnh báo ầm ĩ mỗi khi Qdrant chưa lên. Việc "kho
        # này có sống không" là của `/health`, không phải của constructor.
        check_compatibility=False,
    )
    return Clients(
        mongo=mongo, redis=redis, http=http, qdrant=qdrant, db_name=settings.mongo_db
    )


async def close_clients(clients: Clients) -> None:
    await clients.http.aclose()
    await clients.redis.aclose()
    await clients.qdrant.close()
    clients.mongo.close()
