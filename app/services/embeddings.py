"""Tầng 3 gắn entity: vector game trong Qdrant — `docs/PHASE-6.md` mục 3.

`PROGRESS.md` ghi tầng này còn nợ đúng ba thứ:

> cần quyết định backend sinh vector, một collection Qdrant, và một đợt nạp
> vector cho toàn catalog.

File này là cả ba. Bản trước có một `embedding_match` gọi Qdrant, nhưng
**không có gì từng ghi vào Qdrant** — collection rỗng, nên mọi truy vấn trả về
rỗng và tầng 3 luôn trượt xuống hàng đợi duyệt tay. Nhìn từ ngoài giống hệt
lúc nó còn là stub, chỉ khác là giờ tốn thêm một lượt gọi Gemini mỗi bài.

Ba chốt:

1. **Point id sinh từ `_id` của Mongo, một cách xác định.** Qdrant chỉ nhận id
   là số nguyên hoặc UUID, không nhận chuỗi ObjectId 24 ký tự. Bản trước làm
   ngược lại — `ObjectId(best_hit.id)` — nên kể cả khi collection có dữ liệu
   thì dòng đó vẫn ném `InvalidId`. Ánh xạ phải xác định để nạp lại lần hai
   ghi đè đúng point cũ chứ không nhân đôi.
2. **`game_id` thật nằm trong payload**, không phải trong id. Đó là thứ ta đọc
   ra khi tra ngược.
3. **Nạp lại được, và nạp dở dang được.** Catalog có hàng trăm nghìn entity;
   một lượt job nạp một lô rồi ghi mốc lại trong Mongo, lượt sau chạy tiếp.
   Giữ mốc trong bộ nhớ tiến trình thì worker restart là quay lại từ đầu.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.adapters.llm.gemini import EMBED_DIM

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

COLLECTION = "games"

# Namespace cố định để ObjectId -> UUID luôn ra cùng một kết quả, ở mọi tiến
# trình, mọi lần chạy. Đổi hằng này = mọi point cũ thành mồ côi.
_NAMESPACE = uuid.UUID("6f4d1a2c-3b5e-4c7a-9d81-0e2f5a7b3c96")


def point_id(game_id: ObjectId) -> str:
    """`_id` của Mongo -> id point của Qdrant, xác định và một-đối-một."""
    return str(uuid.uuid5(_NAMESPACE, str(game_id)))


def embedding_text(game: dict[str, Any]) -> str:
    """Đoạn văn bản đại diện cho một game khi đem so vector.

    Chỉ tên và alias, **không** kèm mô tả: bài tin được so với entity qua tên
    game, và nhồi cả đoạn mô tả vào chỉ làm vector trôi về phía thể loại
    ("game nhập vai thế giới mở") — lúc đó mọi tin RPG đều khớp với mọi RPG.
    """
    titles = game.get("titles") or {}
    names = [titles.get("primary"), titles.get("vi"), titles.get("ja")]
    names.extend(game.get("aliases") or [])

    seen: list[str] = []
    for name in names:
        if isinstance(name, str) and name.strip() and name not in seen:
            seen.append(name.strip())
    return " | ".join(seen)


async def ensure_collection(client: AsyncQdrantClient) -> bool:
    """Tạo collection nếu chưa có. Trả về True nếu vừa tạo.

    `COSINE` chứ không phải `DOT`: vector của Gemini không chuẩn hoá sẵn về độ
    dài 1, mà điểm số của `DOT` thì phụ thuộc độ dài — tên game dài sẽ ăn điểm
    cao hơn chỉ vì nó dài.
    """
    if await client.collection_exists(COLLECTION):
        return False
    await client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
    )
    logger.info("đã tạo collection Qdrant", extra={"collection": COLLECTION})
    return True


async def upsert_games(
    client: AsyncQdrantClient, games: list[tuple[ObjectId, str, list[float]]]
) -> int:
    """Ghi vector của một lô game. Trả về số point đã ghi."""
    if not games:
        return 0

    await client.upsert(
        collection_name=COLLECTION,
        points=[
            qmodels.PointStruct(
                id=point_id(game_id),
                vector=vector,
                payload={"game_id": str(game_id), "name": name},
            )
            for game_id, name, vector in games
        ],
    )
    return len(games)


async def search(
    client: AsyncQdrantClient, vector: list[float], *, threshold: float, limit: int = 1
) -> list[tuple[ObjectId, float]]:
    """Tìm entity gần nhất. Trả về [(game_id, điểm)], đã lọc theo ngưỡng."""
    response = await client.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=limit,
        score_threshold=threshold,
        with_payload=True,
    )

    results: list[tuple[ObjectId, float]] = []
    for hit in response.points:
        raw = (hit.payload or {}).get("game_id")
        if not isinstance(raw, str) or not ObjectId.is_valid(raw):
            # Point cũ từ một lần nạp theo lược đồ khác. Bỏ qua, đừng nổ.
            logger.warning("point Qdrant thiếu game_id hợp lệ", extra={"point_id": str(hit.id)})
            continue
        results.append((ObjectId(raw), float(hit.score)))
    return results
