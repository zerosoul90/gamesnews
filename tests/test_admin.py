"""Admin entity — `docs/PHASE-1.md` mục 8.

Ba tầng, tách ra vì hỏng ở mỗi tầng có nghĩa khác nhau:

1. `merge_content` là hàm thuần — luật gộp field, không cần Mongo.
2. Thao tác trên Mongo thật — xoá đúng document, index unique không cản, DLC
   không bị mồ côi.
3. HTTP — token, mã lỗi, và việc thay đổi có được đẩy sang index hay không.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.deps import get_db, get_meili
from app.main import app
from app.models.game import Game, Media, ReleaseDate, Titles
from app.services.admin import (
    AdminError,
    EntityNotFoundError,
    MergeConflictError,
    merge_content,
    merge_games,
    search_entities,
    set_manual_aliases,
    to_object_id,
)
from app.services.catalog import ensure_indexes, games, upsert_game, with_aliases

Db = AsyncIOMotorDatabase[dict[str, Any]]

# Token viết cứng, và ruff nói đúng — nhưng đây là token của test, không mở
# được gì cả.
ADMIN_TOKEN = "token-test-khong-phai-secret-that"  # noqa: S105


def make_game(**overrides: Any) -> Game:
    base: dict[str, Any] = {
        "slug": "elden-ring",
        "titles": Titles(primary="Elden Ring"),
        "external_ids": {"igdb": 119133},
        "platforms": ["pc"],
    }
    return with_aliases(Game(**(base | overrides)))


async def insert(db: Db, game: Game, *, key: str = "igdb") -> ObjectId:
    await upsert_game(db, game, key=key)
    doc = await games(db).find_one({"slug": game.slug})
    assert doc is not None
    object_id: ObjectId = doc["_id"]
    return object_id


# --- luật gộp, không cần Mongo ---------------------------------------------


def test_gop_don_id_ngoai_ve_ben_giu_lai() -> None:
    """Nửa quan trọng nhất của thao tác gộp: sau khi gộp, ID của bên bị gộp
    phải nằm trên entity còn lại. Không thì job đồng bộ của nguồn đó insert lại
    đúng cái entity vừa bị xoá."""
    keep = make_game(external_ids={"igdb": 119133})
    drop = make_game(slug="elden-ring-mobile", external_ids={"google_play": "com.fromsoft.er"})

    merged = merge_content(keep, drop)

    assert merged.external_ids.igdb == 119133
    assert merged.external_ids.google_play == "com.fromsoft.er"


def test_gop_hai_steam_appid_khac_nhau_thi_tu_choi() -> None:
    """Hai AppID khác nhau gần như luôn là hai sản phẩm khác nhau. Gộp bừa thì
    Phase 2 lấy giá của game này gắn cho game kia."""
    keep = make_game(external_ids={"steam_appid": 1245620})
    drop = make_game(slug="khac", external_ids={"steam_appid": 999999})

    with pytest.raises(MergeConflictError) as err:
        merge_content(keep, drop)
    assert "steam_appid" in err.value.fields


def test_gop_hop_nhat_danh_sach_va_khong_mat_du_lieu() -> None:
    keep = make_game(platforms=["pc"], genres=["action"], developers=["FromSoftware"])
    drop = make_game(
        slug="er-console",
        external_ids={"google_play": "com.x"},
        platforms=["ps5"],
        genres=["rpg"],
        developers=["FromSoftware"],
        release_dates=[ReleaseDate(region="jp", date="2022-02-25", platform="ps5")],
        media=Media(cover="https://example.test/cover.jpg"),
        is_live_service=True,
    )

    merged = merge_content(keep, drop)

    assert merged.platforms == ["pc", "ps5"]
    assert merged.genres == ["action", "rpg"]
    assert merged.developers == ["FromSoftware"]  # không nhân đôi
    assert len(merged.release_dates) == 1
    assert merged.media.cover == "https://example.test/cover.jpg"  # bên giữ lại trống thì lấy
    # Một nguồn biết đây là game dịch vụ là đủ; nguồn kia chỉ không có trường đó.
    assert merged.is_live_service is True


def test_gop_sinh_lai_alias_khong_dau_cho_ca_hai_ten() -> None:
    keep = make_game(titles=Titles(primary="Arena of Valor"))
    drop = with_aliases(
        Game(
            slug="lien-quan-mobile",
            titles=Titles(primary="Liên Quân Mobile"),
            external_ids={"google_play": "com.garena.game.kgvn"},
        )
    )

    merged = merge_content(keep, drop)

    assert "Liên Quân Mobile" in merged.aliases
    assert "lien quan mobile" in merged.aliases_normalized
    assert merged.titles.primary == "Arena of Valor"  # bên giữ lại quyết định tên


# --- trên Mongo thật -------------------------------------------------------


async def test_tim_entity_bang_ten_co_dau_va_khong_dau(mongo_db: Db) -> None:
    await insert(mongo_db, make_game(titles=Titles(primary="Liên Quân Mobile")))

    for query in ("lien quan", "Liên Quân", "LIEN QUAN MOBILE"):
        found, total = await search_entities(mongo_db, query)
        assert total == 1, query
        assert found[0]["slug"] == "elden-ring"


async def test_tim_entity_bang_slug_va_bang_id_ngoai(mongo_db: Db) -> None:
    await insert(mongo_db, make_game(external_ids={"igdb": 119133, "steam_appid": 1245620}))

    for query in ("elden-ring", "1245620", "119133"):
        _, total = await search_entities(mongo_db, query)
        assert total == 1, query


async def test_query_rong_liet_ke_entity_sua_gan_nhat(mongo_db: Db) -> None:
    await insert(mongo_db, make_game())
    await insert(mongo_db, make_game(slug="ff7", external_ids={"igdb": 2}))

    found, total = await search_entities(mongo_db, "")

    assert total == 2
    assert found[0]["slug"] == "ff7"  # ghi sau -> updated_at mới hơn -> đứng trước


async def test_sua_alias_sinh_lai_ban_khong_dau(mongo_db: Db) -> None:
    game_id = await insert(mongo_db, make_game())

    doc = await set_manual_aliases(mongo_db, game_id, ["Vòng Elden", "  ", "eldenring"])

    assert "Vòng Elden" in doc["aliases"]
    assert "vong elden" in doc["aliases_normalized"]
    assert "" not in doc["aliases"]  # dòng trắng bị bỏ


async def test_sua_alias_khong_xoa_duoc_ten_chinh(mongo_db: Db) -> None:
    """Alias gõ tay là THÊM, không phải THAY. Admin lỡ tay xoá sạch ô nhập
    cũng không được làm mất tên chính của game."""
    game_id = await insert(mongo_db, make_game())

    doc = await set_manual_aliases(mongo_db, game_id, [])

    assert "Elden Ring" in doc["aliases"]
    assert "elden ring" in doc["aliases_normalized"]


async def test_sua_alias_y_het_thi_khong_doi_updated_at(mongo_db: Db) -> None:
    """Cùng lý lẽ với `content_hash` ở catalog: `updated_at` nhảy vô cớ là job
    reindex delta phải đẩy lại một entity không đổi gì."""
    game_id = await insert(mongo_db, make_game())
    truoc = (await games(mongo_db).find_one({"_id": game_id}) or {})["updated_at"]

    await set_manual_aliases(mongo_db, game_id, ["Elden Ring"])

    sau = (await games(mongo_db).find_one({"_id": game_id}) or {})["updated_at"]
    assert sau == truoc


async def test_gop_xoa_ben_bi_gop_va_ghi_lai_dau_vet(mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    keep_id = await insert(mongo_db, make_game())
    drop_id = await insert(
        mongo_db,
        make_game(slug="elden-ring-vn", external_ids={"google_play": "com.fromsoft.er"}),
        key="google_play",
    )

    doc = await merge_games(mongo_db, keep_id=keep_id, drop_id=drop_id)

    assert await games(mongo_db).count_documents({}) == 1
    assert doc["external_ids"]["google_play"] == "com.fromsoft.er"
    assert doc["merged_from"][0]["_id"] == drop_id
    assert doc["merged_from"][0]["slug"] == "elden-ring-vn"


async def test_gop_xong_job_dong_bo_cu_khong_tao_lai_entity(mongo_db: Db) -> None:
    """Đây là lý do thao tác gộp phải mang theo `external_ids`.

    Sau khi gộp, job của nguồn bên bị gộp vẫn chạy với ID cũ của nó. Nếu ID đó
    không nằm trên entity còn lại thì `upsert_game` không tìm thấy gì và insert
    lại đúng entity ta vừa xoá — công gộp tay đổ sông đổ biển sau một đêm.
    """
    await ensure_indexes(mongo_db)
    keep_id = await insert(mongo_db, make_game())
    mobile = make_game(slug="elden-ring-vn", external_ids={"google_play": "com.fromsoft.er"})
    drop_id = await insert(mongo_db, mobile, key="google_play")

    await merge_games(mongo_db, keep_id=keep_id, drop_id=drop_id)
    outcome = await upsert_game(mongo_db, mobile, key="google_play")

    assert outcome in ("updated", "unchanged")
    assert await games(mongo_db).count_documents({}) == 1


async def test_gop_tro_lai_parent_game_cua_dlc(mongo_db: Db) -> None:
    """DLC trỏ vào entity bị gộp thì sau khi gộp nó phải trỏ vào entity còn
    lại, không thì nó thành mồ côi — trỏ tới một _id không còn tồn tại."""
    await ensure_indexes(mongo_db)
    keep_id = await insert(mongo_db, make_game())
    # Bên bị gộp phải mang ID của NGUỒN KHÁC: hai igdb id khác nhau là xung
    # đột, và test này kiểm chuyện khác — DLC có bị mồ côi không.
    drop_id = await insert(
        mongo_db,
        make_game(slug="elden-ring-2", external_ids={"google_play": "com.fromsoft.er"}),
        key="google_play",
    )
    dlc_id = await insert(
        mongo_db,
        make_game(
            slug="shadow-of-the-erdtree",
            titles=Titles(primary="Shadow of the Erdtree"),
            external_ids={"igdb": 333},
            type="dlc",
            parent_game=drop_id,
        ),
    )

    await merge_games(mongo_db, keep_id=keep_id, drop_id=drop_id)

    dlc = await games(mongo_db).find_one({"_id": dlc_id})
    assert dlc is not None
    assert dlc["parent_game"] == keep_id


async def test_khong_gop_mot_entity_vao_chinh_no(mongo_db: Db) -> None:
    game_id = await insert(mongo_db, make_game())
    with pytest.raises(AdminError):
        await merge_games(mongo_db, keep_id=game_id, drop_id=game_id)


async def test_gop_entity_khong_ton_tai_thi_bao_khong_tim_thay(mongo_db: Db) -> None:
    game_id = await insert(mongo_db, make_game())
    with pytest.raises(EntityNotFoundError):
        await merge_games(mongo_db, keep_id=game_id, drop_id=ObjectId())


def test_id_khong_hop_le_bi_chan_som() -> None:
    with pytest.raises(AdminError):
        to_object_id("không-phải-objectid")


# --- HTTP ------------------------------------------------------------------


class FakeIndex:
    """Ghi lại lời gọi thay vì nói chuyện với Meilisearch.

    Test HTTP ở đây chỉ hỏi một câu: router có đẩy thay đổi sang index không.
    Chất lượng tìm kiếm đã có `test_search.py` chạy trên Meilisearch thật lo.
    """

    def __init__(self) -> None:
        self.added: list[str] = []
        self.deleted: list[str] = []

    async def add_documents(self, documents: list[dict[str, Any]]) -> None:
        self.added += [str(doc["id"]) for doc in documents]

    async def delete_document(self, document_id: str) -> None:
        self.deleted.append(document_id)


@pytest_asyncio.fixture
async def index() -> FakeIndex:
    return FakeIndex()


@pytest_asyncio.fixture
async def client(mongo_db: Db, index: FakeIndex) -> AsyncIterator[httpx.AsyncClient]:
    """Client HTTP gọi thẳng vào ASGI app, cùng event loop với fixture Mongo.

    Không dùng `TestClient`: nó chạy app trong một vòng lặp sự kiện riêng ở
    thread khác, còn client Motor của fixture lại thuộc vòng lặp của test.
    """
    app.dependency_overrides[get_db] = lambda: mongo_db
    app.dependency_overrides[get_meili] = lambda: index
    app.dependency_overrides[get_settings] = lambda: Settings(
        admin_token=SecretStr(ADMIN_TOKEN)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


AUTH = {"X-Admin-Token": ADMIN_TOKEN}


async def test_khong_co_token_thi_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/admin/api/games")).status_code == 401


async def test_token_sai_thi_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/admin/api/games", headers={"X-Admin-Token": "sai"})
    assert response.status_code == 401


async def test_chua_cau_hinh_token_thi_admin_dong_han(client: httpx.AsyncClient) -> None:
    """Mặc định là đóng: một trang sửa được cả catalog mà không có mật khẩu còn
    tệ hơn nhiều so với việc admin tạm thời không vào được."""
    app.dependency_overrides[get_settings] = lambda: Settings(admin_token=SecretStr(""))
    response = await client.get("/admin/api/games", headers=AUTH)
    assert response.status_code == 503


async def test_tim_qua_api(client: httpx.AsyncClient, mongo_db: Db) -> None:
    await insert(mongo_db, make_game())

    response = await client.get("/admin/api/games", params={"q": "elden"}, headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["slug"] == "elden-ring"
    # _id phải ra chuỗi, không phải ObjectId — client không hiểu BSON.
    assert isinstance(body["items"][0]["_id"], str)


async def test_id_sai_dinh_dang_tra_400(client: httpx.AsyncClient) -> None:
    response = await client.get("/admin/api/games/khong-phai-id", headers=AUTH)
    assert response.status_code == 400


async def test_entity_khong_co_tra_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/admin/api/games/{ObjectId()}", headers=AUTH)
    assert response.status_code == 404


async def test_sua_alias_qua_api_va_day_sang_index(
    client: httpx.AsyncClient, mongo_db: Db, index: FakeIndex
) -> None:
    game_id = await insert(mongo_db, make_game())

    response = await client.put(
        f"/admin/api/games/{game_id}/aliases",
        json={"aliases": ["Vòng Elden"]},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert "vong elden" in response.json()["aliases_normalized"]
    assert index.added == [str(game_id)]


async def test_gop_qua_api_go_ben_bi_gop_khoi_index(
    client: httpx.AsyncClient, mongo_db: Db, index: FakeIndex
) -> None:
    await ensure_indexes(mongo_db)
    keep_id = await insert(mongo_db, make_game())
    drop_id = await insert(
        mongo_db,
        make_game(slug="er-vn", external_ids={"google_play": "com.fromsoft.er"}),
        key="google_play",
    )

    response = await client.post(
        "/admin/api/games/merge",
        json={"keep_id": str(keep_id), "drop_id": str(drop_id)},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert index.deleted == [str(drop_id)]
    assert index.added == [str(keep_id)]


async def test_gop_xung_dot_tra_409(client: httpx.AsyncClient, mongo_db: Db) -> None:
    await ensure_indexes(mongo_db)
    keep_id = await insert(
        mongo_db,
        make_game(external_ids={"steam_appid": 1245620}),
        key="steam_appid",
    )
    drop_id = await insert(
        mongo_db,
        make_game(slug="khac", external_ids={"steam_appid": 999999}),
        key="steam_appid",
    )

    response = await client.post(
        "/admin/api/games/merge",
        json={"keep_id": str(keep_id), "drop_id": str(drop_id)},
        headers=AUTH,
    )

    assert response.status_code == 409
    assert "steam_appid" in response.json()["detail"]
    # Xung đột thì không được mất entity nào.
    assert await games(mongo_db).count_documents({}) == 2


# --- nhánh HTML ------------------------------------------------------------


async def test_chua_dang_nhap_thi_bi_day_ve_trang_login(client: httpx.AsyncClient) -> None:
    response = await client.get("/admin")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


async def test_dang_nhap_bang_form_roi_vao_duoc_trang(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    await insert(mongo_db, make_game())

    login = await client.post("/admin/login", data={"token": ADMIN_TOKEN})
    assert login.status_code == 303
    assert client.cookies.get("admin_token") == ADMIN_TOKEN

    page = await client.get("/admin", params={"q": "elden"})
    assert page.status_code == 200
    assert "Elden Ring" in page.text


async def test_dang_nhap_sai_token_thi_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/admin/login", data={"token": "sai"})
    assert response.status_code == 401
    assert client.cookies.get("admin_token") is None


async def test_trang_chi_tiet_hien_alias_va_o_gop(client: httpx.AsyncClient, mongo_db: Db) -> None:
    game_id = await insert(mongo_db, make_game())
    await client.post("/admin/login", data={"token": ADMIN_TOKEN})

    page = await client.get(f"/admin/games/{game_id}")

    assert page.status_code == 200
    assert "elden ring" in page.text  # bản normalized
    assert "drop_id" in page.text  # form gộp


async def test_sua_alias_bang_form_moi_dong_mot_alias(
    client: httpx.AsyncClient, mongo_db: Db
) -> None:
    game_id = await insert(mongo_db, make_game())
    await client.post("/admin/login", data={"token": ADMIN_TOKEN})

    response = await client.post(
        f"/admin/games/{game_id}/aliases",
        data={"aliases": "Vòng Elden\nElden Ring: Nightreign"},
    )

    assert response.status_code == 303
    doc = await games(mongo_db).find_one({"_id": game_id})
    assert doc is not None
    assert "vong elden" in doc["aliases_normalized"]
    # Dấu hai chấm nằm trong tên game thật, nên chỉ tách theo dòng.
    assert "Elden Ring: Nightreign" in doc["aliases"]
