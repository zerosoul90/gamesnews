"""`to_mongo` phải giữ ObjectId là ObjectId — `app/models/game.mongo_document`.

`PlainSerializer` của `PyObjectId` có `when_used="always"`, nên nó chạy cả ở
`mode="python"`. `model_dump()` trần vì thế biến mọi ObjectId thành **chuỗi**,
rồi document đó được ghi thẳng vào Mongo trong khi mọi truy vấn tra bằng
ObjectId. Không bên nào ném lỗi; chúng chỉ không bao giờ khớp nhau.

Bốn tính năng đã chết vì đúng cái này, và không cái nào để lại log:

- `price_alerts.game_id` là chuỗi -> cảnh báo giá không bao giờ bắn;
- `user_follows.target_id` là chuỗi -> push streamer live không tới ai;
- `user_reviews.game_id` là chuỗi -> điểm game luôn bị ẩn;
- `user_badges.user_id` là chuỗi -> badge trao lại mỗi lần review.

Test tham số hoá theo **danh sách model**, không phải theo từng ca: thêm một
model có `PyObjectId` mà quên đi qua `mongo_document` thì file này đỏ ngay.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, get_args

import pytest
from bson import ObjectId
from pydantic import BaseModel

import app.models
from app.models.community import UserBadge, UserReview
from app.models.game import Game, Titles
from app.models.price import PriceCurrent, PriceHistory
from app.models.promotion import Giftcode
from app.models.user import PriceAlert, User, UserFollow, UserLibrary


def instances() -> list[BaseModel]:
    """Một bản mẫu của mọi model có field ObjectId đi xuống Mongo."""
    return [
        # DLC trỏ về game cha bằng `parent_game`; để dạng chuỗi thì trang game
        # không liệt kê được DLC của chính nó.
        Game(slug="shadow-of-the-erdtree", titles=Titles(primary="Shadow of the Erdtree"),
             type="dlc", parent_game=ObjectId()),
        User(steam_id64="76561198000000000"),
        UserLibrary(user_id=ObjectId(), store="steam", game_id=ObjectId(), synced_at="2026-01-01"),
        UserFollow(user_id=ObjectId(), target_type="game", target_id=ObjectId()),
        PriceAlert(user_id=ObjectId(), game_id=ObjectId(), condition="historical_low"),
        UserReview(user_id=ObjectId(), game_id=ObjectId(), score=8),
        UserBadge(user_id=ObjectId(), badge_type="reviewer"),
        Giftcode(game_id=ObjectId(), code="TET2026"),
        PriceCurrent(
            game_id=ObjectId(),
            store="steam",
            price_initial=100,
            price_final=50,
            discount_percent=50,
        ),
        PriceHistory(
            game_id=ObjectId(), store="steam", price_final=50, discount_percent=50, changed_at="x"
        ),
    ]


def objectid_fields(model: BaseModel) -> dict[str, ObjectId]:
    """Field nào của bản mẫu này thật sự đang giữ một ObjectId."""
    found: dict[str, ObjectId] = {}
    for name, field in type(model).model_fields.items():
        value = getattr(model, name, None)
        if isinstance(value, ObjectId):
            found[field.alias or name] = value
    return found


@pytest.mark.parametrize("model", instances(), ids=lambda m: type(m).__name__)
def test_to_mongo_giu_nguyen_objectid(model: BaseModel) -> None:
    doc: dict[str, Any] = model.to_mongo()  # type: ignore[attr-defined]
    expected = objectid_fields(model)
    assert expected, f"{type(model).__name__} không có field ObjectId nào để kiểm"

    for key, value in expected.items():
        assert key in doc, f"{type(model).__name__}.to_mongo() thiếu {key!r}"
        assert isinstance(doc[key], ObjectId), (
            f"{type(model).__name__}.{key} ra {type(doc[key]).__name__}, "
            "phải là ObjectId — Mongo tra bằng ObjectId, không tra bằng chuỗi"
        )
        assert doc[key] == value


def test_union_giu_chuoi_van_la_chuoi() -> None:
    """`UserFollow.target_id` nhận cả ObjectId lẫn slug; đừng ép nhầm chiều."""
    follow = UserFollow(user_id=ObjectId(), target_type="series", target_id="dark-souls")
    assert follow.to_mongo()["target_id"] == "dark-souls"


def test_alias_duoc_ton_trong() -> None:
    """`User.id` ghi xuống dưới tên `_id`, đúng khoá chính của Mongo."""
    doc = User().to_mongo()
    assert isinstance(doc["_id"], ObjectId)
    assert "id" not in doc


def _mentions_objectid(annotation: object) -> bool:
    """Annotation này có dính `ObjectId` ở đâu đó không?

    Pydantic **gỡ `Annotated` ra** khi dựng `model_fields`, nên
    `field.annotation` của một `PyObjectId` là `bson.ObjectId` trần, không phải
    alias `PyObjectId`. So sánh với `PyObjectId` thì không bao giờ khớp — và
    một chốt "chống bỏ sót" không bao giờ khớp là một chốt không tồn tại.
    Union thì `Annotated` còn nguyên trong `__args__`, nên phải soi đệ quy.
    """
    if annotation is ObjectId:
        return True
    return any(_mentions_objectid(arg) for arg in get_args(annotation))


def models_with_objectid() -> list[str]:
    """Mọi model có `to_mongo` và có ít nhất một field ObjectId."""
    names: list[str] = []
    for info in pkgutil.iter_modules(app.models.__path__):
        module = importlib.import_module(f"app.models.{info.name}")
        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type) or not issubclass(obj, BaseModel):
                continue
            if obj.__module__ != module.__name__ or not hasattr(obj, "to_mongo"):
                continue
            if any(_mentions_objectid(f.annotation) for f in obj.model_fields.values()):
                names.append(name)
    return names


def test_cach_nhan_dien_thuc_su_tim_ra_model() -> None:
    """Kiểm chính cái chốt bên dưới.

    Bản đầu của nó so `field.annotation is PyObjectId`, không khớp cái gì, nên
    nó xanh vĩnh viễn mà không kiểm gì cả. Test này bắt đúng kiểu "chốt rỗng"
    đó: nếu cách nhận diện lại hỏng thì đây đỏ trước.
    """
    found = models_with_objectid()
    assert {"PriceAlert", "UserReview", "UserFollow", "PriceCurrent"} <= set(found)


def test_moi_model_dung_objectid_deu_co_trong_danh_sach() -> None:
    """Chốt chống bỏ sót: thêm model mới mà quên thêm vào đây thì đỏ."""
    covered = {type(model).__name__ for model in instances()}
    missing = sorted(set(models_with_objectid()) - covered)

    assert not missing, f"model có ObjectId nhưng chưa được kiểm to_mongo: {missing}"
