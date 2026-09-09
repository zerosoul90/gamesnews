"""Serialize document Mongo ra JSON — `app/core/serialization.py`.

Test này tồn tại vì một lỗi **không** unit test nào lúc đó bắt được: mọi
endpoint trả thẳng document Mongo (`/deals`, `/free-games`, `/promotions/*`,
`/community/users/{id}/badges`) đều 500 ngay khi có dữ liệu thật, vì FastAPI
serialize bằng pydantic và pydantic không biết `ObjectId` là gì. Test của
service thì xanh, vì chúng gọi service chứ không đi qua HTTP.

Nên ở đây có cả một test đi qua HTTP thật, không chỉ test hàm thuần.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.serialization import jsonify, jsonify_docs


def test_objectid_thanh_chuoi() -> None:
    oid = ObjectId()
    assert jsonify(oid) == str(oid)


def test_datetime_thanh_iso() -> None:
    moment = dt.datetime(2026, 9, 9, 13, 30, tzinfo=dt.UTC)
    assert jsonify(moment) == "2026-09-09T13:30:00+00:00"


def test_lan_sau_vao_dict_va_list_long_nhau() -> None:
    inner = ObjectId()
    value = {"a": [{"game_id": inner}], "b": {"c": {"d": inner}}}

    assert jsonify(value) == {"a": [{"game_id": str(inner)}], "b": {"c": {"d": str(inner)}}}


def test_giu_nguyen_kieu_json_hop_le() -> None:
    value = {"n": 1, "f": 1.5, "s": "x", "b": True, "none": None, "list": [1, 2]}
    assert jsonify(value) == value


def test_khong_doi_thu_tu_khoa() -> None:
    """Thứ tự khoá là thứ tự client đọc được; đổi nó là đổi hợp đồng API."""
    value = {"z": 1, "a": 2, "m": ObjectId()}
    assert list(jsonify(value).keys()) == ["z", "a", "m"]


def test_endpoint_tra_document_mongo_khong_con_500() -> None:
    """Chốt thật: đây chính là kịch bản đã làm bốn endpoint chết."""
    app = FastAPI()

    @app.get("/vo-hieu")
    async def raw() -> list[dict[str, Any]]:
        return [{"_id": ObjectId(), "game_id": ObjectId()}]

    @app.get("/da-sua")
    async def wrapped() -> list[dict[str, Any]]:
        return jsonify_docs([{"_id": ObjectId(), "game_id": ObjectId()}])

    with TestClient(app, raise_server_exceptions=False) as client:
        # Bản chưa sửa PHẢI đỏ — nếu ngày nào đó FastAPI tự xử lý được ObjectId
        # thì test này đỏ và ta biết mà bỏ bớt lớp bọc, thay vì giữ mãi.
        assert client.get("/vo-hieu").status_code == 500

        response = client.get("/da-sua")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body[0]["game_id"], str)
        assert ObjectId.is_valid(body[0]["game_id"])
