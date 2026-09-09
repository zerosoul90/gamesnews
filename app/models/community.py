import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from app.models.game import PyObjectId


class UserReview(BaseModel):
    """Đánh giá của người dùng cho một game"""
    user_id: PyObjectId
    game_id: PyObjectId
    score: int = Field(ge=1, le=10)
    comment: str | None = None
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

class UserBadge(BaseModel):
    """Danh hiệu người dùng (badge)"""
    user_id: PyObjectId
    badge_type: str # VD: 'first_blood', 'reviewer', 'wiki_editor'
    earned_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
