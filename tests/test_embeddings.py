"""Vector game trong Qdrant — `app/services/embeddings.py`.

Không dựng Qdrant thật ở đây: phần đáng kiểm là **ánh xạ id** và **văn bản đem
đi embed**, và cả hai đều thuần. Bản trước sai đúng ở hai chỗ đó — nó nhét
chuỗi ObjectId làm point id (Qdrant chỉ nhận số nguyên hoặc UUID) rồi đọc ngược
bằng `ObjectId(hit.id)`, nên kể cả khi collection có dữ liệu thì dòng đó vẫn
ném `InvalidId`.
"""

from __future__ import annotations

import uuid

from bson import ObjectId

from app.services.embeddings import embedding_text, point_id


def test_point_id_la_uuid_hop_le() -> None:
    """Qdrant từ chối id là chuỗi tuỳ ý; phải là số nguyên hoặc UUID."""
    value = point_id(ObjectId())
    assert uuid.UUID(value)


def test_point_id_xac_dinh() -> None:
    """Nạp lại lần hai phải ghi đè point cũ, không nhân đôi."""
    oid = ObjectId()
    assert point_id(oid) == point_id(oid)


def test_hai_game_khac_nhau_ra_hai_point_khac_nhau() -> None:
    assert point_id(ObjectId()) != point_id(ObjectId())


def test_van_ban_gom_moi_ten_va_alias() -> None:
    text = embedding_text(
        {
            "titles": {"primary": "Black Myth: Wukong", "vi": "Hắc Thần Thoại: Ngộ Không"},
            "aliases": ["Wukong"],
        }
    )
    assert "Black Myth: Wukong" in text
    assert "Hắc Thần Thoại: Ngộ Không" in text
    assert "Wukong" in text


def test_khong_lap_lai_ten_trung() -> None:
    text = embedding_text({"titles": {"primary": "Dota 2"}, "aliases": ["Dota 2", "Dota 2"]})
    assert text.count("Dota 2") == 1


def test_bo_qua_gia_tri_rong_va_khong_phai_chuoi() -> None:
    text = embedding_text(
        {"titles": {"primary": "Elden Ring", "vi": None, "ja": "   "}, "aliases": [None, 42, ""]}
    )
    assert text == "Elden Ring"


def test_game_khong_co_ten_thi_van_ban_rong() -> None:
    """Job nạp vector dựa vào chuỗi rỗng để bỏ qua entity, không được nổ."""
    assert embedding_text({}) == ""
    assert embedding_text({"titles": {}, "aliases": []}) == ""
