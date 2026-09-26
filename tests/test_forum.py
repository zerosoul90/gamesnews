"""Diễn đàn — `docs/FORUM.md`.

Đi qua ASGI app thật với Mongo + Redis thật: cổng đăng bài là chuỗi dependency
của FastAPI (JWT → beta → biệt danh), chặn tần suất là script Lua trong Redis,
và chống trùng biệt danh là index unique của Mongo. Gọi thẳng hàm service thì
bỏ qua đúng ba thứ đó.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.main import app
from app.services import forum
from app.services.auth import create_jwt_token

Db = AsyncIOMotorDatabase[dict[str, Any]]

ADMIN_TOKEN = "test-admin-token-forum"  # noqa: S105


@dataclass
class ClientsGia:
    db: Db
    redis: Redis


@dataclass
class Moi:
    http: httpx.AsyncClient
    db: Db
    settings: Settings


@pytest_asyncio.fixture
async def moi(mongo_db: Db, redis_client: Redis) -> AsyncIterator[Moi]:
    await forum.ensure_indexes(mongo_db)
    settings = Settings(admin_token=SecretStr(ADMIN_TOKEN), forum_open=False)
    cu = getattr(app.state, "clients", None)
    app.state.clients = ClientsGia(db=mongo_db, redis=redis_client)
    app.dependency_overrides[get_settings] = lambda: settings
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield Moi(http=http, db=mongo_db, settings=settings)
    app.dependency_overrides.pop(get_settings, None)
    if cu is None:
        del app.state.clients
    else:
        app.state.clients = cu


TU_DONG = "__tu_dong__"


async def tao_user(
    db: Db, *, nickname: str | None = TU_DONG, access: bool = True
) -> dict[str, str]:
    """User thật trong Mongo + header JWT thật của user đó.

    Biệt danh mặc định phải khác nhau giữa các user: index unique chặn trùng
    ngay cả khi ghi thẳng vào Mongo."""
    steam_id = str(ObjectId())
    if nickname == TU_DONG:
        nickname = f"Người Chơi {steam_id[-8:]}"
    doc: dict[str, Any] = {"steam_id64": steam_id, "forum_access": access}
    if nickname is not None:
        doc |= {"nickname": nickname, "nickname_key": forum.nickname_key(nickname)}
    result = await db.users.insert_one(doc)
    return {"Authorization": f"Bearer {create_jwt_token(user_id=str(result.inserted_id))}"}


async def tao_chu_de(m: Moi, headers: dict[str, str], **extra: Any) -> str:
    body = {"category": "thao-luan-chung", "title": "Elden Ring có đáng mua?", "body": "Hỏi thật"}
    res = await m.http.post("/api/v1/forum/threads", json=body | extra, headers=headers)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


# --- Biệt danh -------------------------------------------------------------------


async def test_dat_biet_danh_roi_van_bi_chan_vi_beta_kin(moi: Moi) -> None:
    headers = await tao_user(moi.db, nickname=None, access=False)

    res = await moi.http.put(
        "/api/v1/forum/me/nickname", json={"nickname": "  Trần   Văn  "}, headers=headers
    )

    assert res.status_code == 200, res.text
    assert res.json()["nickname"] == "Trần Văn"
    assert res.json()["can_post"] is False
    assert "beta" in res.json()["reason"]


async def test_them_dau_hay_dau_cham_khong_gia_danh_duoc(moi: Moi) -> None:
    """Không có bước kiểm trước nào trong code: chỉ index unique trên
    `nickname_key` chặn được. Test này đỏ nếu index không được dựng."""
    await tao_user(moi.db, nickname="Trần Văn")
    ke_gia = await tao_user(moi.db, nickname=None)

    for ten in ["tran.van", "TRANVAN", "Tràn_Vân"]:
        res = await moi.http.put(
            "/api/v1/forum/me/nickname", json={"nickname": ten}, headers=ke_gia
        )
        assert res.status_code == 409, ten


async def test_biet_danh_sai_luat(moi: Moi) -> None:
    headers = await tao_user(moi.db, nickname=None)

    for ten in ["ab", "<script>", "a" * 25, "._-a", "Admin", "GamesNews Official", "Kiểm Duyệt 01"]:
        res = await moi.http.put(
            "/api/v1/forum/me/nickname", json={"nickname": ten}, headers=headers
        )
        assert res.status_code == 422, ten


async def test_doi_biet_danh_30_ngay_mot_lan_nhung_sua_hoa_thuong_thi_duoc(moi: Moi) -> None:
    headers = await tao_user(moi.db, nickname=None)
    url = "/api/v1/forum/me/nickname"
    assert (
        await moi.http.put(url, json={"nickname": "Rong Den"}, headers=headers)
    ).status_code == 200

    # Cùng khoá: chỉ là sửa cách viết, không tính lượt đổi.
    assert (
        await moi.http.put(url, json={"nickname": "Rồng Đen"}, headers=headers)
    ).status_code == 200
    # Khác khoá trong vòng 30 ngày.
    assert (
        await moi.http.put(url, json={"nickname": "Rong Trang"}, headers=headers)
    ).status_code == 409


# --- Cổng đăng bài ---------------------------------------------------------------


async def test_khong_dang_nhap_thi_khong_dang_duoc(moi: Moi) -> None:
    res = await moi.http.post(
        "/api/v1/forum/threads",
        json={"category": "thao-luan-chung", "title": "Tiêu đề đủ dài", "body": "x"},
    )
    assert res.status_code in (401, 403)


async def test_beta_kin_chi_nguoi_duoc_cap_quyen_moi_dang(moi: Moi) -> None:
    ngoai = await tao_user(moi.db, access=False)
    trong = await tao_user(moi.db, access=True)
    body = {"category": "hoi-dap", "title": "Máy yếu chơi được không", "body": "GTX 1050"}

    assert (
        await moi.http.post("/api/v1/forum/threads", json=body, headers=ngoai)
    ).status_code == 403
    assert (
        await moi.http.post("/api/v1/forum/threads", json=body, headers=trong)
    ).status_code == 201

    # Mở công khai thì người chưa được cấp quyền cũng đăng được.
    moi.settings.forum_open = True
    assert (
        await moi.http.post("/api/v1/forum/threads", json=body, headers=ngoai)
    ).status_code == 201


async def test_chua_co_biet_danh_thi_chua_dang_duoc(moi: Moi) -> None:
    headers = await tao_user(moi.db, nickname=None, access=True)
    res = await moi.http.post(
        "/api/v1/forum/threads",
        json={"category": "hoi-dap", "title": "Tiêu đề đủ dài", "body": "x"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "biệt danh" in res.json()["detail"]


async def test_admin_cap_quyen_theo_steam_id(moi: Moi) -> None:
    await moi.db.users.insert_one({"steam_id64": "76561190000000001"})
    url = "/admin/api/forum/access"
    admin = {"X-Admin-Token": ADMIN_TOKEN}

    assert (await moi.http.post(url, json={"steam_id64": "76561190000000001"})).status_code == 401
    res = await moi.http.post(url, json={"steam_id64": "76561190000000001"}, headers=admin)
    assert res.status_code == 200, res.text
    doc = await moi.db.users.find_one({"steam_id64": "76561190000000001"})
    assert doc is not None and doc["forum_access"] is True

    res = await moi.http.post(url, json={"steam_id64": "chua-dang-nhap-bao-gio"}, headers=admin)
    assert res.status_code == 404


# --- Chủ đề ----------------------------------------------------------------------


async def test_danh_sach_hien_biet_danh_va_khong_lo_steam_id(moi: Moi) -> None:
    headers = await tao_user(moi.db, nickname="Rồng Đen")
    await tao_chu_de(moi, headers)

    res = await moi.http.get("/api/v1/forum/threads", params={"category": "thao-luan-chung"})

    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["author"]["nickname"] == "Rồng Đen"
    user = await moi.db.users.find_one({"nickname": "Rồng Đen"})
    assert user is not None
    # Quét cả chuỗi JSON, không chỉ một field: lộ ở bất cứ đâu cũng là lộ.
    assert user["steam_id64"] not in res.text
    assert "body" not in item


async def test_chu_de_phai_thuoc_dung_mot_noi(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    game_id = (
        await moi.db.games.insert_one({"slug": "elden-ring", "titles": {"primary": "Elden Ring"}})
    ).inserted_id
    url = "/api/v1/forum/threads"
    base = {"title": "Tiêu đề đủ dài", "body": "x"}

    assert (await moi.http.post(url, json=base, headers=headers)).status_code == 422
    res = await moi.http.post(
        url, json=base | {"category": "hoi-dap", "game_id": str(game_id)}, headers=headers
    )
    assert res.status_code == 422
    assert (
        await moi.http.post(url, json=base | {"category": "khong-co"}, headers=headers)
    ).status_code == 404
    assert (
        await moi.http.post(url, json=base | {"game_id": str(ObjectId())}, headers=headers)
    ).status_code == 404

    thread_id = await tao_chu_de(moi, headers, category=None, game_id=str(game_id))
    res = await moi.http.get("/api/v1/forum/threads", params={"game_id": str(game_id)})
    assert [t["id"] for t in res.json()["items"]] == [thread_id]
    assert res.json()["items"][0]["game"]["title"] == "Elden Ring"


async def test_tieu_de_va_noi_dung_duoc_lam_sach_o_bien(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    url = "/api/v1/forum/threads"
    base = {"category": "hoi-dap"}

    assert (
        await moi.http.post(url, json=base | {"title": "abc", "body": "x"}, headers=headers)
    ).status_code == 422
    assert (
        await moi.http.post(
            url, json=base | {"title": "Đủ dài rồi", "body": "   "}, headers=headers
        )
    ).status_code == 422

    thread_id = await tao_chu_de(
        moi, headers, title="  Hai   khoảng  trắng  ", body="  dòng 1\ndòng 2  "
    )
    res = await moi.http.get(f"/api/v1/forum/threads/{thread_id}")
    assert res.json()["thread"]["title"] == "Hai khoảng trắng"
    # Xuống dòng là định dạng duy nhất của text thuần — không được gộp mất.
    assert res.json()["thread"]["body"] == "dòng 1\ndòng 2"


# --- Trả lời ---------------------------------------------------------------------


async def test_tra_loi_day_chu_de_len_dau(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    cu = await tao_chu_de(moi, headers, title="Chủ đề cũ hơn")
    await tao_chu_de(moi, headers, title="Chủ đề mới hơn")

    res = await moi.http.post(
        f"/api/v1/forum/threads/{cu}/posts", json={"body": "up"}, headers=headers
    )
    assert res.status_code == 201

    items = (
        await moi.http.get("/api/v1/forum/threads", params={"category": "thao-luan-chung"})
    ).json()["items"]
    assert items[0]["id"] == cu
    assert items[0]["reply_count"] == 1


async def test_trich_dan(moi: Moi) -> None:
    a = await tao_user(moi.db, nickname="Người A")
    b = await tao_user(moi.db, nickname="Người B")
    t1 = await tao_chu_de(moi, a)
    t2 = await tao_chu_de(moi, a, title="Một chủ đề khác")
    goc = (
        await moi.http.post(
            f"/api/v1/forum/threads/{t1}/posts", json={"body": "bài gốc"}, headers=a
        )
    ).json()["id"]

    # Trích bài của chủ đề khác: sai chỗ.
    res = await moi.http.post(
        f"/api/v1/forum/threads/{t2}/posts", json={"body": "x", "quote_post_id": goc}, headers=b
    )
    assert res.status_code == 404

    res = await moi.http.post(
        f"/api/v1/forum/threads/{t1}/posts",
        json={"body": "đồng ý", "quote_post_id": goc},
        headers=b,
    )
    assert res.status_code == 201
    posts = (await moi.http.get(f"/api/v1/forum/threads/{t1}")).json()["posts"]
    assert posts[1]["quote"]["body"] == "bài gốc"
    assert posts[1]["quote"]["author"]["nickname"] == "Người A"

    # Bài gốc bị xoá thì trích dẫn không còn là đường vòng để đọc nó.
    assert (await moi.http.delete(f"/api/v1/forum/posts/{goc}", headers=a)).status_code == 204
    posts = (await moi.http.get(f"/api/v1/forum/threads/{t1}")).json()["posts"]
    assert posts[0]["quote"] == {"id": goc, "author": None, "body": None}


async def test_chu_de_khoa_thi_khong_tra_loi_duoc(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    thread_id = await tao_chu_de(moi, headers)
    await moi.db[forum.THREADS].update_one({"_id": ObjectId(thread_id)}, {"$set": {"locked": True}})

    res = await moi.http.post(
        f"/api/v1/forum/threads/{thread_id}/posts", json={"body": "x"}, headers=headers
    )
    assert res.status_code == 409


# --- Sửa / xoá -------------------------------------------------------------------


async def test_chi_nguoi_viet_moi_sua_xoa_duoc(moi: Moi) -> None:
    chu = await tao_user(moi.db, nickname="Chủ Bài")
    la = await tao_user(moi.db, nickname="Người Lạ")
    thread_id = await tao_chu_de(moi, chu)
    url = f"/api/v1/forum/threads/{thread_id}"

    assert (
        await moi.http.patch(url, json={"title": "Bị sửa bởi người lạ"}, headers=la)
    ).status_code == 403
    assert (await moi.http.delete(url, headers=la)).status_code == 403

    assert (await moi.http.patch(url, json={"body": "đã sửa"}, headers=chu)).status_code == 204
    res = await moi.http.get(url)
    assert res.json()["thread"]["body"] == "đã sửa"
    assert res.json()["thread"]["edited_at"] is not None

    assert (await moi.http.delete(url, headers=chu)).status_code == 204
    assert (await moi.http.get(url)).status_code == 404
    doc = await moi.db[forum.THREADS].find_one({"_id": ObjectId(thread_id)})
    # Xoá mềm: kiểm duyệt vẫn tra được.
    assert doc is not None and doc["status"] == forum.DELETED


async def test_xoa_tra_loi_thi_giam_dem(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    thread_id = await tao_chu_de(moi, headers)
    post_id = (
        await moi.http.post(
            f"/api/v1/forum/threads/{thread_id}/posts", json={"body": "x"}, headers=headers
        )
    ).json()["id"]

    await moi.http.delete(f"/api/v1/forum/posts/{post_id}", headers=headers)

    res = await moi.http.get(f"/api/v1/forum/threads/{thread_id}")
    assert res.json()["thread"]["reply_count"] == 0
    assert res.json()["posts"] == []


# --- Báo cáo ---------------------------------------------------------------------


async def test_ba_nguoi_bao_cao_thi_bai_tu_an(moi: Moi) -> None:
    chu = await tao_user(moi.db, nickname="Chủ Bài")
    thread_id = await tao_chu_de(moi, chu)
    bao = {"target_type": "thread", "target_id": thread_id, "reason": "spam"}
    nguoi = [await tao_user(moi.db, nickname=f"Người {i:02d}") for i in range(3)]

    # Tự báo cáo bài mình: vô nghĩa, và là cách tự ẩn bài để né sửa.
    assert (await moi.http.post("/api/v1/forum/reports", json=bao, headers=chu)).status_code == 422

    r1 = await moi.http.post("/api/v1/forum/reports", json=bao, headers=nguoi[0])
    assert r1.json() == {"hidden": False}
    # Cùng một người báo hai lần không được tính là hai.
    assert (
        await moi.http.post("/api/v1/forum/reports", json=bao, headers=nguoi[0])
    ).status_code == 409
    assert (await moi.http.get(f"/api/v1/forum/threads/{thread_id}")).status_code == 200

    await moi.http.post("/api/v1/forum/reports", json=bao, headers=nguoi[1])
    r3 = await moi.http.post("/api/v1/forum/reports", json=bao, headers=nguoi[2])

    assert r3.json() == {"hidden": True}
    assert (await moi.http.get(f"/api/v1/forum/threads/{thread_id}")).status_code == 404
    items = (
        await moi.http.get("/api/v1/forum/threads", params={"category": "thao-luan-chung"})
    ).json()["items"]
    assert items == []


# --- Chặn tần suất ---------------------------------------------------------------


async def test_chu_de_thu_sau_trong_mot_gio_bi_chan(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    for i in range(5):
        await tao_chu_de(moi, headers, title=f"Chủ đề số {i}")

    res = await moi.http.post(
        "/api/v1/forum/threads",
        json={"category": "hoi-dap", "title": "Chủ đề thứ sáu", "body": "x"},
        headers=headers,
    )
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) > 0


async def test_request_sai_khong_dot_luot_cua_nguoi_dung(moi: Moi) -> None:
    """Token lấy SAU khi request hợp lệ. Lấy trước thì gõ nhầm chuyên mục năm
    lần là bị khoá một giờ mà chưa đăng được bài nào."""
    headers = await tao_user(moi.db)
    for _ in range(5):
        res = await moi.http.post(
            "/api/v1/forum/threads",
            json={"category": "khong-co", "title": "Tiêu đề đủ dài", "body": "x"},
            headers=headers,
        )
        assert res.status_code == 404

    for i in range(5):
        await tao_chu_de(moi, headers, title=f"Chủ đề số {i}")


# --- Chuyên mục ------------------------------------------------------------------


async def test_chuyen_muc_dem_dung_so_chu_de_hien(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    await tao_chu_de(moi, headers)
    xoa = await tao_chu_de(moi, headers, title="Sẽ bị xoá")
    await moi.http.delete(f"/api/v1/forum/threads/{xoa}", headers=headers)

    res = await moi.http.get("/api/v1/forum/categories")

    dem = {c["slug"]: c["thread_count"] for c in res.json()}
    assert dem["thao-luan-chung"] == 1
    assert dem["hoi-dap"] == 0
    assert set(dem) == forum.category_slugs()


def test_file_chuyen_muc_hop_le() -> None:
    """Slug đi thẳng vào URL và vào Mongo; trùng hay có ký tự lạ là hỏng cả hai."""
    slugs = [c["slug"] for c in forum.categories()]
    assert len(slugs) == len(set(slugs))
    for c in forum.categories():
        assert c["slug"] == c["slug"].lower() and " " not in c["slug"], c
        assert c["name"] and c["description"], c
    assert json.dumps(slugs)  # đọc được thành JSON sạch


async def test_moc_thoi_gian_co_mui_gio(moi: Moi) -> None:
    headers = await tao_user(moi.db)
    thread_id = await tao_chu_de(moi, headers)
    created = (await moi.http.get(f"/api/v1/forum/threads/{thread_id}")).json()["thread"][
        "created_at"
    ]
    # Không có múi giờ thì trình duyệt hiểu là giờ địa phương — lệch 7 tiếng.
    assert dt.datetime.fromisoformat(created).tzinfo is not None
