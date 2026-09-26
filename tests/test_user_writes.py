"""Hai đường GHI cá nhân hoá — `POST /api/v1/user/alerts` và `.../follows`.

Trước đây cả hai nhận thẳng `PriceAlert` / `UserFollow` làm schema body. Hai
model ấy khai `user_id` là **bắt buộc**, nhưng router ghi đè nó bằng claim `sub`
của JWT ngay dòng sau. Hệ quả:

- Client không gửi `user_id` thì ăn 422 — cho một trường server không dùng. Web
  không gọi nổi endpoint nếu không bịa một giá trị.
- Trường ấy hiện trong OpenAPI như thể đặt được. Nó bị bỏ qua, nhưng một bản
  sửa sau lỡ bỏ dòng ghi đè là thành lỗ leo thang quyền ngay.

Không có test nào chạm tới hai endpoint này trước file này — 646 test xanh nói
đúng 0 điều về chúng.

Test đi qua ASGI app thật chứ không gọi hàm: phần hỏng nằm ở **tầng schema của
FastAPI**, mà gọi thẳng hàm thì bỏ qua đúng tầng đó.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.main import app
from app.services.auth import create_jwt_token
from app.services.user_reads import follows_of

Db = AsyncIOMotorDatabase[dict[str, Any]]


@dataclass
class ClientsGia:
    """Đủ để `request.app.state.clients.db` chạy. Hai endpoint này không đụng
    tới redis/http/qdrant, nên dựng cả `Clients` thật chỉ để lấy `.db` là thừa."""

    db: Db


@pytest_asyncio.fixture
async def client(mongo_db: Db) -> AsyncIterator[httpx.AsyncClient]:
    cu = getattr(app.state, "clients", None)
    app.state.clients = ClientsGia(db=mongo_db)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    if cu is None:
        del app.state.clients
    else:
        app.state.clients = cu


def auth(user_id: ObjectId) -> dict[str, str]:
    """Token thật, ký bằng đúng secret mà `get_current_user` dùng để giải mã.

    Không override dependency: làm thế thì phần "router lấy chủ sở hữu từ JWT"
    — đúng thứ đang kiểm — bị thay bằng một hằng số của test.
    """
    return {"Authorization": f"Bearer {create_jwt_token(user_id=str(user_id))}"}


# --- alerts ------------------------------------------------------------------


async def test_dat_canh_bao_khong_can_gui_user_id(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Thân request chỉ có dữ liệu của chính cảnh báo.

    Đỏ trước khi sửa: `PriceAlert` đòi `user_id`, nên FastAPI trả 422.
    """
    user_id = ObjectId()
    game_id = ObjectId()

    res = await client.post(
        "/api/v1/user/alerts",
        json={"game_id": str(game_id), "condition": "historical_low"},
        headers=auth(user_id),
    )

    assert res.status_code == 200, res.text
    doc = await mongo_db.price_alerts.find_one({"game_id": game_id})
    assert doc is not None
    assert doc["user_id"] == user_id


async def test_canh_bao_luon_thuoc_ve_nguoi_gui_token(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    """Gửi kèm `user_id` của người khác cũng không đổi được chủ sở hữu.

    Đây là chốt chặn leo thang quyền: `user_id` không còn nằm trong schema nên
    Pydantic bỏ qua trường thừa, và chủ sở hữu chỉ có thể tới từ JWT.
    """
    toi = ObjectId()
    nguoi_khac = ObjectId()
    game_id = ObjectId()

    res = await client.post(
        "/api/v1/user/alerts",
        json={
            "game_id": str(game_id),
            "condition": "historical_low",
            "user_id": str(nguoi_khac),
        },
        headers=auth(toi),
    )

    assert res.status_code == 200, res.text
    doc = await mongo_db.price_alerts.find_one({"game_id": game_id})
    assert doc is not None
    assert doc["user_id"] == toi
    assert await mongo_db.price_alerts.count_documents({"user_id": nguoi_khac}) == 0


async def test_condition_la_thi_422_chu_khong_phai_500(client: httpx.AsyncClient) -> None:
    """Giá trị lạ bị chặn ở biên.

    Khai `condition: str` thì nó lọt qua FastAPI rồi chết trong constructor
    Pydantic — 500 cho một lỗi rõ ràng là của client.
    """
    res = await client.post(
        "/api/v1/user/alerts",
        json={"game_id": str(ObjectId()), "condition": "khi_nao_toi_thich"},
        headers=auth(ObjectId()),
    )

    assert res.status_code == 422


async def test_game_id_sai_dang_thi_400(client: httpx.AsyncClient) -> None:
    """`game_id` không phải ObjectId là lỗi client, không phải sự cố server."""
    res = await client.post(
        "/api/v1/user/alerts",
        json={"game_id": "khong-phai-objectid", "condition": "historical_low"},
        headers=auth(ObjectId()),
    )

    assert res.status_code == 400


# --- follows -----------------------------------------------------------------


async def test_theo_doi_game_luu_objectid_de_join_duoc(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    """`target_id` của game phải lưu dạng ObjectId.

    Lưu chuỗi thì `follows_of` không join được với `games`, và danh sách theo
    dõi hiện một chuỗi hex trần thay vì tên game — hỏng im lặng, vì endpoint
    vẫn trả 200. Nên test khẳng định qua chính `follows_of`, không chỉ qua mã
    trạng thái.
    """
    user_id = ObjectId()
    game_id = ObjectId()
    await mongo_db.games.insert_one(
        {"_id": game_id, "titles": {"primary": "Hades II"}, "slug": "hades-ii"}
    )

    res = await client.post(
        "/api/v1/user/follows",
        json={"target_type": "game", "target_id": str(game_id)},
        headers=auth(user_id),
    )

    assert res.status_code == 200, res.text
    doc = await mongo_db.user_follows.find_one({"user_id": user_id})
    assert doc is not None
    assert doc["target_id"] == game_id  # ObjectId, không phải str

    follows = await follows_of(mongo_db, user_id)
    assert follows[0]["target"] is not None
    assert follows[0]["target"]["title"] == "Hades II"


async def test_theo_doi_khong_phai_game_giu_nguyen_chuoi(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    """Series/streamer định danh bằng slug hoặc tên, không ép sang ObjectId."""
    user_id = ObjectId()

    res = await client.post(
        "/api/v1/user/follows",
        json={"target_type": "series", "target_id": "the-witcher"},
        headers=auth(user_id),
    )

    assert res.status_code == 200, res.text
    doc = await mongo_db.user_follows.find_one({"user_id": user_id})
    assert doc is not None
    assert doc["target_id"] == "the-witcher"


async def test_target_type_la_thi_422(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/api/v1/user/follows",
        json={"target_type": "con_meo", "target_id": "abc"},
        headers=auth(ObjectId()),
    )

    assert res.status_code == 422


async def test_khong_co_token_thi_401(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/api/v1/user/alerts",
        json={"game_id": str(ObjectId()), "condition": "historical_low"},
    )

    assert res.status_code == 401


# --- return_to của Steam OpenID ----------------------------------------------


async def test_return_to_tro_vao_trang_spa_khong_phai_endpoint_json(
    client: httpx.AsyncClient,
) -> None:
    """`openid.return_to` phải là route của Angular.

    Gọi qua chính endpoint chứ không gọi `get_steam_openid_url` với một chuỗi
    tự bịa: phần có thể sai nằm ở chỗ **router ghép đường dẫn**, mà truyền tay
    một `return_to` đúng rồi kiểm nó vẫn đúng thì test xanh kể cả khi router
    ghép sai — xanh mà không chứng minh gì.

    Hai cách sai, cả hai chỉ lộ ra ở bước cuối của đăng nhập:

    - Trỏ vào `/api/v1/auth/steam/callback`: Express của web chỉ proxy tiền tố
      `/api` và **cắt bỏ** tiền tố ấy, nên backend nhận `/v1/auth/steam/callback`
      → 404.
    - Kể cả tới được endpoint thì nó trả JSON, và người dùng kết thúc đăng nhập
      trước một cục `{"access_token": ...}` — token không vào được ứng dụng.
    """
    res = await client.get("/api/v1/auth/steam/login", follow_redirects=False)

    assert res.status_code == 307
    dich = urllib.parse.urlparse(res.headers["location"])
    tham_so = urllib.parse.parse_qs(dich.query)
    return_to = tham_so["openid.return_to"][0]

    assert urllib.parse.urlparse(return_to).path == "/auth/steam/callback"
    assert "/api/" not in return_to

    # `realm` phải là gốc origin, nếu không Steam từ chối.
    assert tham_so["openid.realm"][0] == f"{urllib.parse.urlparse(return_to).scheme}://{
        urllib.parse.urlparse(return_to).netloc
    }/"


# --- cài đặt thông báo -------------------------------------------------------


async def test_cai_dat_mac_dinh_cho_user_chua_tung_luu(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    """User cũ thiếu hẳn kênh thêm sau (`forum_reply`) vẫn nhận đủ khoá, đúng
    giá trị gatekeeper dùng khi khoá vắng mặt."""
    user_id = (await mongo_db.users.insert_one({"steam_id64": "1"})).inserted_id

    res = await client.get("/api/v1/user/notification-settings", headers=auth(user_id))

    assert res.status_code == 200
    assert res.json() == {
        "quiet_hours": {"from": "22:00", "to": "07:00"},
        "channels": {
            "price_alert": True,
            "streamer_live": True,
            "forum_reply": True,
            "news_digest": "daily",
        },
    }


async def test_luu_cai_dat_roi_doc_lai_va_luu_dung_khoa_gatekeeper_doc(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    user_id = (await mongo_db.users.insert_one({"steam_id64": "1"})).inserted_id
    body = {
        "quiet_hours": {"from": "23:30", "to": "06:00"},
        "channels": {
            "price_alert": False,
            "streamer_live": True,
            "forum_reply": False,
            "news_digest": "weekly",
        },
    }

    res = await client.put("/api/v1/user/notification-settings", json=body, headers=auth(user_id))
    assert res.status_code == 200
    assert res.json() == body

    # Khoá phải là `from`/`to` — dạng `services/notification.py` đọc. Ghi ra
    # `from_time` thì gatekeeper lặng lẽ rơi về 22:00-07:00.
    doc = await mongo_db.users.find_one({"_id": user_id})
    assert doc is not None
    assert doc["notification_settings"]["quiet_hours"] == {"from": "23:30", "to": "06:00"}
    res = await client.get("/api/v1/user/notification-settings", headers=auth(user_id))
    assert res.json() == body


async def test_gio_sai_dinh_dang_bi_tu_choi(client: httpx.AsyncClient, mongo_db: Db) -> None:
    """Gatekeeper coi giờ không parse được là "không có giờ im lặng" — lưu một
    giờ sai là âm thầm tắt giờ im lặng của người dùng."""
    user_id = (await mongo_db.users.insert_one({"steam_id64": "1"})).inserted_id
    body = {
        "quiet_hours": {"from": "25:00", "to": "7h"},
        "channels": {
            "price_alert": True,
            "streamer_live": True,
            "forum_reply": True,
            "news_digest": "daily",
        },
    }

    res = await client.put("/api/v1/user/notification-settings", json=body, headers=auth(user_id))

    assert res.status_code == 422


async def test_cai_dat_can_dang_nhap(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/v1/user/notification-settings")
    assert res.status_code in (401, 403)
