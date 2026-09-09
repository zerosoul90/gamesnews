from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user_id
from app.core.deps import MongoDep
from app.core.serialization import jsonify_docs
from app.models.community import UserReview
from app.services.community import award_badge, calculate_game_score

router = APIRouter(prefix="/community", tags=["community"])


class ReviewRequest(BaseModel):
    """Thân request của `POST /community/reviews`.

    Bản trước nhận `dict[str, Any]` rồi tự kiểm bằng tay, và cách kiểm đó có
    hai lỗ: `if not score` coi **điểm 0 là thiếu điểm**, và không có gì chặn
    `score = 999` hay `score = -3` đi thẳng vào phép tính trung bình. Khai
    model để pydantic chặn ngay ở biên và OpenAPI mô tả đúng.
    """

    game_id: str
    # Khớp đúng ràng buộc của `UserReview`: sai lệch ở đây thì request qua được
    # biên API rồi mới chết ở tầng model, và client nhận 500 thay vì 422.
    score: int = Field(ge=1, le=10)
    comment: str | None = None


@router.post("/reviews")
async def post_review(
    review_data: ReviewRequest,
    db: MongoDep,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Đăng hoặc sửa review cho 1 game"""
    if not ObjectId.is_valid(review_data.game_id):
        raise HTTPException(status_code=400, detail="game_id không hợp lệ")

    game_id = ObjectId(review_data.game_id)
    review = UserReview(
        user_id=ObjectId(user_id),
        game_id=game_id,
        score=review_data.score,
        comment=review_data.comment,
    )

    await db.user_reviews.update_one(
        {"user_id": ObjectId(user_id), "game_id": game_id},
        {"$set": review.to_mongo()},
        upsert=True,
    )

    # Trao badge 'reviewer' cho bài đánh giá đầu tiên
    await award_badge(db, user_id, "reviewer")

    return {"status": "success"}


@router.get("/games/{game_id}/reviews/score")
async def get_game_score(game_id: str, db: MongoDep) -> dict[str, Any]:
    """Điểm trung bình của game. Dưới 20 lượt thì `average_score` là null."""
    if not ObjectId.is_valid(game_id):
        raise HTTPException(status_code=400, detail="game_id không hợp lệ")
    score = await calculate_game_score(db, game_id)
    # Service luôn trả dict; giữ nhánh này để mypy thấy kiểu thu hẹp đúng.
    return score or {"average_score": None, "review_count": 0, "is_hidden": True}


@router.get("/users/{user_id}/badges")
async def get_user_badges(user_id: str, db: MongoDep) -> list[dict[str, Any]]:
    """Xem danh hiệu của 1 user"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="user_id không hợp lệ")
    cursor = db.user_badges.find({"user_id": ObjectId(user_id)})
    return jsonify_docs(await cursor.to_list(length=100))
