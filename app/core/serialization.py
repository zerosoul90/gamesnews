"""Đưa document Mongo về dạng JSON trả được ra ngoài.

Vì sao cần: FastAPI serialize response bằng pydantic. Một endpoint khai
`-> dict[str, Any]` rồi trả thẳng document Mongo sẽ **500** ngay khi document
có `ObjectId` — mà gần như document nào cũng có (`_id`, `game_id`, `user_id`).
Lỗi này không lộ ra trong unit test nào gọi thẳng service; nó chỉ hiện khi có
dữ liệu thật và đi qua HTTP, tức là đúng lúc bắt đầu test thật.

Chiếu `{"_id": 0}` không cứu được: `game_id` vẫn là ObjectId. Nên chỗ sửa đúng
là ở biên trả về, một lần, cho mọi endpoint.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from bson import ObjectId


def jsonify(value: Any) -> Any:
    """Đổi ObjectId thành chuỗi và datetime thành ISO, đệ quy.

    Giữ nguyên mọi kiểu JSON đã hợp lệ. Không đụng tới cấu trúc: dict vẫn là
    dict, list vẫn là list, thứ tự khoá không đổi.
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonify(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonify(item) for item in value]
    return value


def jsonify_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`jsonify` cho một danh sách document, giữ đúng kiểu để mypy soi được."""
    return [jsonify(doc) for doc in docs]
