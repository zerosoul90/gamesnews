"""Đẩy push FCM và sổ token thiết bị — `docs/PHASE-3.md`.

Không gọi ra FCM thật: kiểm bằng `httpx.MockTransport`, nên test soi được đúng
những thứ hay sai mà không cần dự án Firebase — hình dạng request, cache access
token, và cách phân biệt "hỏng tạm thời" với "token chết hẳn".

Điều KHÔNG kiểm được ở đây: cú gọi cuối tới `fcm.googleapis.com`. Muốn kiểm thì
phải có service account thật.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.adapters.fcm.adapter import FcmAdapter
from app.services import devices

Db = AsyncIOMotorDatabase[dict[str, Any]]


def make_key() -> str:
    """Sinh khoá RSA thật lúc chạy test, không cắm khoá cứng vào repo."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def adapter(handler: Any, *, key: str | None = None) -> FcmAdapter:
    return FcmAdapter(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        project_id="du-an-test",
        client_email="test@du-an-test.iam.gserviceaccount.com",
        private_key=key if key is not None else make_key(),
    )


def ok_handler(calls: list[httpx.Request]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "oauth2" in str(request.url):
            return httpx.Response(200, json={"access_token": "token-gia", "expires_in": 3599})
        return httpx.Response(200, json={"name": "projects/du-an-test/messages/1"})

    return handler


# --- cấu hình --------------------------------------------------------------


def test_thieu_cau_hinh_thi_bao_chua_san_sang() -> None:
    """Không cấu hình mà vẫn báo gửi thành công là đúng cái bẫy của bản mock."""
    empty = FcmAdapter(httpx.AsyncClient(), project_id="", client_email="", private_key="")

    assert empty.configured is False


def test_khoa_co_xuong_dong_thoat_van_dung_duoc() -> None:
    """Khoá trong JSON service account đi qua biến môi trường thành "\\n" theo
    nghĩa đen. Không hoàn nguyên thì PyJWT báo khoá sai định dạng."""
    key = make_key()
    escaped = key.replace("\n", "\\n")

    client = FcmAdapter(
        httpx.AsyncClient(), project_id="p", client_email="e", private_key=escaped
    )

    assert client.configured is True


# --- gửi -------------------------------------------------------------------


async def test_gui_thanh_cong_dung_dinh_dang_v1() -> None:
    calls: list[httpx.Request] = []

    result = await adapter(ok_handler(calls)).send(
        "token-thiet-bi", title="Giảm giá!", body="Elden Ring còn 300k", data={"game_id": "abc"}
    )

    assert result.ok is True
    # Cú đầu là đổi JWT lấy access token, cú sau mới là gửi.
    assert "oauth2.googleapis.com" in str(calls[0].url)
    assert "fcm.googleapis.com/v1/projects/du-an-test/messages:send" in str(calls[1].url)
    assert calls[1].headers["Authorization"] == "Bearer token-gia"

    body = json.loads(calls[1].content)["message"]
    # S105 báo nhầm ở dòng dưới: đây là token thiết bị của test, không phải
    # mật khẩu.
    assert body["token"] == "token-thiet-bi"  # noqa: S105
    assert body["notification"]["title"] == "Giảm giá!"


async def test_data_bi_ep_ve_chuoi() -> None:
    """FCM chỉ nhận chuỗi trong `data`; một số hay bool lọt vào là 400 cho cả
    tin nhắn."""
    calls: list[httpx.Request] = []

    await adapter(ok_handler(calls)).send(
        "t", title="x", body="y", data={"count": 3, "sale": True}
    )

    assert json.loads(calls[1].content)["message"]["data"] == {"count": "3", "sale": "True"}


async def test_access_token_duoc_dung_lai() -> None:
    """Gửi cho 500 người mà xin 500 lần token thì phần lớn thời gian là chờ
    OAuth."""
    calls: list[httpx.Request] = []
    client = adapter(ok_handler(calls))

    for _ in range(3):
        await client.send("t", title="x", body="y")

    oauth_calls = [c for c in calls if "oauth2" in str(c.url)]
    assert len(oauth_calls) == 1


async def test_token_chet_duoc_bao_rieng_khong_phai_loi_thuong() -> None:
    """Mạng chập chờn thì thử lại lần sau; token chết thì thử lại vô ích và
    phải xoá đi. Hai chuyện khác nhau."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3599})
        return httpx.Response(404, json={"error": {"status": "UNREGISTERED"}})

    result = await adapter(handler).send("token-da-chet", title="x", body="y")

    assert result.ok is False
    assert result.token_is_dead is True


async def test_loi_may_chu_khong_bi_coi_la_token_chet() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3599})
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})

    result = await adapter(handler).send("token-tot", title="x", body="y")

    assert result.ok is False
    assert result.token_is_dead is False


# --- sổ thiết bị -----------------------------------------------------------


async def test_dang_ky_thiet_bi_va_tra_ve_token(mongo_db: Db) -> None:
    await devices.ensure_indexes(mongo_db)
    user = ObjectId()

    assert await devices.register(mongo_db, user, "token-a") is True
    assert await devices.register(mongo_db, user, "token-b") is True

    assert sorted(await devices.tokens_of(mongo_db, user)) == ["token-a", "token-b"]


async def test_dang_ky_lai_cung_token_khong_nhan_doi(mongo_db: Db) -> None:
    await devices.ensure_indexes(mongo_db)
    user = ObjectId()

    assert await devices.register(mongo_db, user, "token-a") is True
    assert await devices.register(mongo_db, user, "token-a") is False

    assert await devices.tokens_of(mongo_db, user) == ["token-a"]


async def test_may_doi_chu_thi_chuyen_token_sang_chu_moi(mongo_db: Db) -> None:
    """Không chuyển thì chủ cũ vẫn nhận thông báo trên máy đã bán đi."""
    await devices.ensure_indexes(mongo_db)
    cu, moi = ObjectId(), ObjectId()
    await devices.register(mongo_db, cu, "token-chung")

    await devices.register(mongo_db, moi, "token-chung")

    assert await devices.tokens_of(mongo_db, cu) == []
    assert await devices.tokens_of(mongo_db, moi) == ["token-chung"]


async def test_xoa_token_chet(mongo_db: Db) -> None:
    await devices.ensure_indexes(mongo_db)
    user = ObjectId()
    await devices.register(mongo_db, user, "token-a")

    assert await devices.forget(mongo_db, "token-a") is True
    assert await devices.forget(mongo_db, "token-a") is False
    assert await devices.tokens_of(mongo_db, user) == []


async def test_xoa_moi_thiet_bi_cua_mot_user(mongo_db: Db) -> None:
    """Dùng khi người dùng yêu cầu xoá dữ liệu."""
    await devices.ensure_indexes(mongo_db)
    user = ObjectId()
    await devices.register(mongo_db, user, "token-a")
    await devices.register(mongo_db, user, "token-b")

    assert await devices.forget_all(mongo_db, user) == 2
    assert await devices.tokens_of(mongo_db, user) == []


async def test_token_rong_bi_tu_choi(mongo_db: Db) -> None:
    await devices.ensure_indexes(mongo_db)
    with pytest.raises(ValueError):
        await devices.register(mongo_db, ObjectId(), "   ")
