from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

Db = AsyncIOMotorDatabase[dict[str, Any]]

async def generate_year_in_review(db: Db, user_id: str, year: int) -> dict[str, Any] | None:
    """
    Thống kê thư viện và tổng kết cuối năm cho User (Wrapped).
    Dữ liệu đầu vào lấy từ user_library.
    Lưu ý: Thời gian chơi có thể liên tục cập nhật, do đó kết quả này được tính động.
    """
    pipeline: list[dict[str, Any]] = [
        {"$match": {"user_id": ObjectId(user_id)}},
        {"$sort": {"playtime_minutes": -1}}
    ]

    cursor = db.user_library.aggregate(pipeline)
    library = await cursor.to_list(length=1000)

    if not library:
        return None

    total_playtime = sum(item.get("playtime_minutes", 0) for item in library)

    # Lấy thông tin game cho top 5
    top_5 = library[:5]
    top_games = []

    for item in top_5:
        game_id = item.get("game_id")
        playtime = item.get("playtime_minutes", 0)

        game = await db.games.find_one({"_id": game_id}, {"titles": 1})
        title = game.get("titles", {}).get("primary", "Unknown Game") if game else "Unknown Game"

        top_games.append({
            "game_id": str(game_id),
            "title": title,
            "playtime_minutes": playtime
        })

    # Giả định thêm: ta có thể đếm thể loại yêu thích nhất bằng cách map với games.genres

    return {
        "year": year,
        "total_games_played": len([g for g in library if g.get("playtime_minutes", 0) > 0]),
        "total_playtime_minutes": total_playtime,
        "top_games": top_games,
        "message": "Năm nay bạn đã cày cuốc rất nỗ lực!"
    }
