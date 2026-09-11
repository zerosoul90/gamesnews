"""Trang chi tiết game: tra theo slug, trả đủ dữ liệu cho một lần render.

Mọi route per-game sẵn có đều nhận `game_id` là ObjectId, nên web không có
đường nào đi từ `/game/:slug` tới dữ liệu — slug là thứ duy nhất nó có trong
URL. Đây là chỗ bù vào.

Gộp game + giá + lịch sử giá + điểm cộng đồng vào **một** response thay vì để
web gọi bốn lần. SSR render trên server nên mỗi lần gọi là một round-trip nằm
thẳng trong thời gian chờ của người dùng, và ba trong bốn lần đó phải đợi lần
đầu trả về mới biết `game_id` để gọi tiếp.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import MongoDep
from app.core.serialization import jsonify_docs
from app.services.community import calculate_game_score
from app.services.reviews import review_score_of
from app.services.rollup import DAILY

router = APIRouter(tags=["Games"])

# Kênh CCU trong time-series. `job_fetch_steam_ccu` ghi đúng tên này.
CCU_CHANNEL = "steam_ccu"

# Chỉ lấy field trang này dùng. Trả thẳng document thì lộ `aliases_normalized`,
# `content_hash` và mọi thứ thêm sau này — nội bộ của hệ thống khớp entity,
# không phải API công khai.
_PROJECTION = {
    "slug": 1,
    "titles": 1,
    "type": 1,
    "series": 1,
    "platforms": 1,
    "genres": 1,
    "developers": 1,
    "publishers": 1,
    "release_dates": 1,
    "is_live_service": 1,
    "current_season": 1,
    "media.cover": 1,
    "media.screenshots": 1,
    "system_requirements": 1,
    "region_locked_vn": 1,
    "external_ids.steam_appid": 1,
}


async def _daily_player_counts(db: Any, game_id: Any, days: int) -> list[dict[str, Any]]:
    """Số người chơi đồng thời theo từng ngày, từ bảng gộp `game_metrics_1d`.

    Đọc mức NGÀY chứ không đọc raw: raw giữ 15 phút một điểm nên 30 ngày là
    ~2.880 điểm cho một game — vẽ ra cùng một đường nhưng tải về gấp 90 lần.
    Bảng ngày lại giữ vĩnh viễn, còn raw bị job rollup xoá theo chính sách giữ
    dữ liệu của SCHEMA.md, nên đây cũng là nguồn duy nhất trả lời được câu
    "tháng trước bao nhiêu người chơi".

    Hai điều dễ sai về kiểu, khác hẳn `price_history` ngay bên trên:

    - `_id.bucket` là `datetime` thật (bắt buộc với time-series của Mongo), nên
      mốc cắt phải là datetime. Truyền chuỗi ISO như bảng giá thì so sánh không
      khớp kiểu và trả về rỗng — im lặng, không lỗi.
    - `_id.game_id` là **chuỗi**, không phải ObjectId (xem `MetricMeta`). Tra
      bằng ObjectId cũng ra rỗng, cũng im lặng.
    """
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    cursor = (
        db[DAILY]
        .find(
            {
                "_id.game_id": str(game_id),
                "_id.channel": CCU_CHANNEL,
                "_id.bucket": {"$gte": cutoff},
            }
        )
        .sort("_id.bucket", 1)
    )

    out: list[dict[str, Any]] = []
    async for row in cursor:
        bucket = row["_id"]["bucket"]
        out.append(
            {
                # Bucket ngày, nên trả ngày thôi: giờ/phút trong đó luôn là
                # 00:00 và chỉ làm client tưởng có độ phân giải cao hơn thật.
                "date": bucket.date().isoformat(),
                # CCU là số người. Làm tròn `avg`: 68681.666 không có nghĩa gì
                # hơn 68682, mà lại đẩy rác vào payload và vào nhãn biểu đồ.
                "avg": round(row["avg"]) if row.get("avg") is not None else None,
                "peak": row.get("peak"),
                "min": row.get("min"),
                "max": row.get("max"),
                # Số lần đo thật trong ngày. Ngày mà job chỉ chạy được 1 lượt
                # không nên bị đọc ngang với ngày đủ 96 lượt.
                "samples": row.get("samples"),
            }
        )
    return out


@router.get("/games/by-slug/{slug}")
async def get_game_by_slug(
    slug: str,
    db: MongoDep,
    region: str = Query("vn", description="Region của bảng giá"),
    history_days: int = Query(30, ge=1, le=365),
    ccu_days: int = Query(30, ge=1, le=365, description="Số ngày CCU theo mức ngày"),
) -> dict[str, Any]:
    """Dữ liệu cho trang `/game/:slug` của web."""
    doc = await db.games.find_one({"slug": slug}, _PROJECTION)
    if not doc:
        # 404 chứ không phải trả rỗng: web dựa vào status này để trang trả đúng
        # 404 kèm `noindex`, thay vì 200 cho một slug bịa.
        raise HTTPException(status_code=404, detail="Game not found")

    game_id = doc["_id"]

    # MỘT region cho cả bảng giá. Lấy mọi region rồi sort theo `price_final` là
    # so 19000 VND với 4.99 USD bằng phép so số: "rẻ nhất" sẽ luôn là store nào
    # báo giá bằng đồng tiền mệnh giá nhỏ, bất kể nó đắt hay rẻ thật.
    price_cursor = db.price_current.find({"game_id": game_id, "region": region}, {"_id": 0}).sort(
        "price_final", 1
    )
    prices = await price_cursor.to_list(None)

    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=history_days)).isoformat()
    history_cursor = db.price_history.find(
        {"game_id": game_id, "region": region, "changed_at": {"$gte": cutoff}}, {"_id": 0}
    ).sort("changed_at", 1)
    history = await history_cursor.to_list(None)

    score = await calculate_game_score(db, str(game_id)) or {
        "average_score": None,
        "review_count": 0,
        "is_hidden": True,
    }

    player_counts = await _daily_player_counts(db, game_id, ccu_days)
    # Tách hẳn khỏi `community_score`: đây là điểm của người dùng Steam, thang
    # khác, nhóm người khác. Gộp hai thứ vào một con số là nói với người đọc một
    # điều không nguồn nào nói.
    steam_review = await review_score_of(db, game_id, "steam")

    titles = doc.get("titles") or {}
    media = doc.get("media") or {}
    return {
        "id": str(game_id),
        "slug": doc["slug"],
        # Tên tiếng Việt trước, như `/deals` — trang này để người Việt đọc.
        "title": titles.get("vi") or titles.get("primary"),
        "title_primary": titles.get("primary"),
        "type": doc.get("type"),
        "series": doc.get("series"),
        "platforms": doc.get("platforms") or [],
        "genres": doc.get("genres") or [],
        "developers": doc.get("developers") or [],
        "publishers": doc.get("publishers") or [],
        "release_dates": doc.get("release_dates") or [],
        "is_live_service": bool(doc.get("is_live_service")),
        "current_season": doc.get("current_season"),
        "cover_image_url": media.get("cover"),
        "screenshots": media.get("screenshots") or [],
        "system_requirements": doc.get("system_requirements") or {"minimum": {}, "recommended": {}},
        "region_locked_vn": bool(doc.get("region_locked_vn")),
        # Để web dựng link "Mua trên Steam". `price_current` không có URL store,
        # và appid là thứ duy nhất đủ để suy ra một URL không bịa.
        "steam_appid": (doc.get("external_ids") or {}).get("steam_appid"),
        "region": region,
        "prices": jsonify_docs(prices),
        "price_history": jsonify_docs(history),
        "community_score": score,
        # None khi chưa đọc được lần nào. Không trả `{"score": 0}` — trang sẽ
        # hiện "0/10" và người đọc hiểu là game bị chấm 0 điểm.
        "steam_review": steam_review,
        "player_counts": player_counts,
    }
