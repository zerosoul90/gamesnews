"""Chỉ số hot — `docs/PHASE-7.md` mục 5.

`SCHEMA.md`: "Chuẩn hoá về percentile trước khi gán trọng số — CCU đơn vị
triệu, bài Reddit đơn vị trăm." Cộng thẳng số tuyệt đối thì CCU nuốt sạch mọi
kênh khác và bảng xếp hạng chỉ còn là bảng CCU.

## Vì sao hàm chính tính cho CẢ catalog, không tính cho từng game

Bản trước có `calculate_hotness(db, game_id)` trả về percentile viết cứng
(`{"steam_ccu": 0.85, ...}`). Không chỉ là dữ liệu giả — **hình dạng hàm đó
không tính percentile được**: percentile của một game là vị trí của nó trong
toàn bộ quần thể, nên muốn biết một game đứng đâu thì phải đọc hết. Gọi từng
game một là đọc lại cả quần thể N lần cho N game.

Vì vậy `compute_hotness` chạy một lượt cho toàn bộ, còn `hotness_of` chỉ đọc
kết quả đã tính sẵn ra khỏi `game_hotness`.

## Hai bảng, hai ý nghĩa

`PHASE-7.md` yêu cầu tách bạch, và checkpoint ghi rõ bảng "Đang tăng mạnh"
không được bị game top thường trực chiếm chỗ:

- `score_absolute` — percentile hiện tại, cho bảng **Phổ biến nhất**.
- `score_momentum` — chênh lệch percentile so với 7 ngày trước, cho bảng
  **Đang tăng mạnh**. Dota 2 luôn ở percentile ~0.99 nên momentum của nó luôn
  quanh 0; một game nhỏ nhảy từ 0.3 lên 0.8 mới là thứ bảng này cần nêu.

Hệ quả cần biết của việc momentum tính trên percentile: nó đo **đổi thứ hạng**,
không đo tăng trưởng tuyệt đối. Một game tăng gấp trăm lần mà cả quần thể cũng
tăng chừng đó thì momentum vẫn bằng 0 — và đó là điều đúng, vì bảng này để trả
lời "game nào đang nổi lên so với phần còn lại", không phải "game nào có con
số tăng nhiều nhất".
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.metrics import GameHotness, GameMetric, MetricMeta
from app.services.rollup import DAILY, RAW

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

HOTNESS = "game_hotness"

# Cửa sổ chuẩn hoá, theo `PHASE-7.md` mục 5.
WINDOW_DAYS = 30
# Mốc so sánh cho momentum.
MOMENTUM_DAYS = 7

# Trọng số từng kênh. Tổng bằng 1 khi đủ cả ba; thiếu kênh nào thì chuẩn hoá
# lại theo tổng trọng số thật sự có dữ liệu, nếu không game chỉ có CCU sẽ luôn
# thua game có đủ ba kênh dù đông hơn hẳn.
CHANNEL_WEIGHTS: dict[str, float] = {
    "steam_ccu": 0.5,
    "twitch_viewers": 0.3,
    "vn_articles": 0.2,
}


def percentiles(values: dict[Any, float]) -> dict[Any, float]:
    """Vị trí tương đối của từng giá trị trong quần thể, trong khoảng (0, 1].

    Dùng định nghĩa "tỉ lệ phần tử nhỏ hơn hoặc bằng". Giá trị bằng nhau nhận
    cùng một percentile — nếu không thì thứ tự đọc từ database quyết định game
    nào hot hơn, mà thứ tự đó thì tuỳ lúc.
    """
    if not values:
        return {}
    ordered = sorted(values.values())
    total = len(ordered)

    # Đếm sẵn hạng của từng giá trị thay vì quét lại quần thể cho từng game:
    # N^2 với 185.000 game là không chạy nổi.
    rank_of: dict[float, int] = {}
    for index, value in enumerate(ordered, start=1):
        rank_of[value] = index

    return {key: rank_of[value] / total for key, value in values.items()}


async def _channel_values(
    db: Db, channel: str, *, since: dt.datetime, until: dt.datetime
) -> dict[Any, float]:
    """Giá trị đại diện của từng game ở một kênh, trong một cửa sổ thời gian.

    Lấy **trung bình các mức đỉnh theo ngày**: đỉnh phản ánh đúng lúc game đông
    nhất, còn trung bình qua nhiều ngày thì một hôm bất thường (ra bản mở rộng,
    một streamer lớn chơi thử) không kéo lệch cả cửa sổ.
    """
    pipeline: list[dict[str, Any]] = [
        {"$match": {"_id.channel": channel, "_id.bucket": {"$gte": since, "$lt": until}}},
        {"$group": {"_id": "$_id.game_id", "value": {"$avg": "$peak"}}},
    ]
    return {
        doc["_id"]: float(doc["value"])
        async for doc in db[DAILY].aggregate(pipeline)
        if doc.get("value") is not None
    }


async def _scores_at(db: Db, *, since: dt.datetime, until: dt.datetime) -> dict[Any, float]:
    """Điểm tổng hợp của từng game trong một cửa sổ."""
    weighted: dict[Any, float] = {}
    weights: dict[Any, float] = {}

    for channel, weight in CHANNEL_WEIGHTS.items():
        values = await _channel_values(db, channel, since=since, until=until)
        for game_id, percentile in percentiles(values).items():
            weighted[game_id] = weighted.get(game_id, 0.0) + percentile * weight
            weights[game_id] = weights.get(game_id, 0.0) + weight

    return {game_id: weighted[game_id] / weights[game_id] for game_id in weighted}


async def compute_hotness(db: Db, *, now: dt.datetime | None = None) -> int:
    """Tính lại chỉ số hot cho toàn bộ game có dữ liệu. Trả về số game đã ghi."""
    now = now or dt.datetime.now(dt.UTC)
    window_start = now - dt.timedelta(days=WINDOW_DAYS)
    past_end = now - dt.timedelta(days=MOMENTUM_DAYS)

    current = await _scores_at(db, since=window_start, until=now)
    if not current:
        logger.info("chưa có dữ liệu time-series để tính chỉ số hot")
        return 0

    # Cùng độ dài cửa sổ, chỉ lùi lại 7 ngày. So hai cửa sổ khác độ dài thì
    # chênh lệch phản ánh độ dài cửa sổ chứ không phản ánh game.
    previous = await _scores_at(
        db, since=past_end - dt.timedelta(days=WINDOW_DAYS), until=past_end
    )

    ccu_recent = await _channel_values(
        db, "steam_ccu", since=now - dt.timedelta(days=1), until=now
    )
    per_channel = {
        channel: percentiles(await _channel_values(db, channel, since=window_start, until=now))
        for channel in CHANNEL_WEIGHTS
    }

    written = 0
    for game_id, score in current.items():
        scores = {
            channel: round(values[game_id], 4)
            for channel, values in per_channel.items()
            if game_id in values
        }
        hotness = GameHotness(
            game_id=str(game_id),
            scores=scores,
            score_absolute=round(score, 4),
            # Chỉ tính chiều đi lên: game tụt hạng không thuộc bảng "Đang tăng
            # mạnh", và số âm ở đó chỉ làm nhiễu khi sắp xếp.
            score_momentum=round(max(0.0, score - previous.get(game_id, score)), 4),
            ccu_now=int(ccu_recent.get(game_id, 0)),
            ccu_peak_24h=int(ccu_recent.get(game_id, 0)),
            computed_at=now.isoformat(),
        )
        await db[HOTNESS].update_one(
            {"game_id": hotness.game_id}, {"$set": hotness.to_mongo()}, upsert=True
        )
        written += 1

    logger.info("tính xong chỉ số hot", extra={"games": written})
    return written


async def hotness_of(db: Db, game_id: str) -> dict[str, Any] | None:
    """Đọc chỉ số đã tính sẵn. Không tính lại — xem docstring đầu file."""
    doc: dict[str, Any] | None = await db[HOTNESS].find_one({"game_id": game_id})
    return doc


async def top_games(
    db: Db, *, by: str = "score_absolute", limit: int = 50
) -> list[dict[str, Any]]:
    """Bảng "Phổ biến nhất" (`score_absolute`) hoặc "Đang tăng mạnh"
    (`score_momentum`)."""
    if by not in ("score_absolute", "score_momentum"):
        raise ValueError(f"không xếp hạng theo {by!r}")
    cursor = db[HOTNESS].find({}).sort(by, -1).limit(limit)
    return [doc async for doc in cursor]


async def update_game_metric(
    db: Db, game_id: str, channel: str, value: int, *, ts: dt.datetime | None = None
) -> None:
    """Ghi một điểm đo vào `game_metrics`. `ts` chỉ truyền vào trong test."""
    metric = GameMetric(
        ts=ts or dt.datetime.now(dt.UTC),
        meta=MetricMeta(game_id=game_id, channel=channel),
        value=value,
    )
    await db[RAW].insert_one(metric.to_mongo())
