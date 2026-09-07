"""Model `games` — xem app/models/game.py và docs/SCHEMA.md mục 1."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models.game import Game, ReleaseDate, Titles


def make_game(**overrides: Any) -> Game:
    base: dict[str, Any] = {
        "slug": "elden-ring",
        "titles": Titles(primary="Elden Ring", ja="エルデンリング"),
        "external_ids": {"igdb": 119133, "steam_appid": 1245620},
        "release_dates": [ReleaseDate(region="ww", date="2022-02-25", platform="pc")],
    }
    return Game(**(base | overrides))


# --- content_hash ---------------------------------------------------------


def test_hash_giong_nhau_cho_hai_model_giong_het() -> None:
    assert make_game().content_hash() == make_game().content_hash()


def test_hash_doi_khi_noi_dung_doi() -> None:
    assert make_game().content_hash() != make_game(genres=["action-rpg"]).content_hash()


def test_hash_khong_doi_khi_dung_lai_du_lieu_da_ghi() -> None:
    """Vòng đời thật: đọc document lên, dựng lại model, băm lại phải ra y hệt.

    Đây mới là điều kiện để "chỉ ghi khi nội dung đổi" hoạt động. Nếu một field
    nào đó đi qua `to_mongo` rồi quay lại mà lệch kiểu, hash sẽ khác và mọi lần
    chạy job đều ghi đè toàn bộ catalog.
    """
    game = make_game()
    khoi_phuc = Game(**game.to_mongo())
    assert khoi_phuc.content_hash() == game.content_hash()


# --- release_year ---------------------------------------------------------


def test_release_year_lay_nam_som_nhat() -> None:
    game = make_game(
        release_dates=[
            ReleaseDate(region="ww", date="2022-02-25", platform="pc"),
            ReleaseDate(region="jp", date="2021-11-01", platform="ps5"),
        ]
    )
    assert game.release_year == 2021


def test_release_year_chap_nhan_ngay_chi_co_nam() -> None:
    """Nguồn ngoài thường chỉ biết mỗi năm phát hành."""
    game = make_game(release_dates=[ReleaseDate(region="ww", date="2022")])
    assert game.release_year == 2022


def test_release_year_none_khi_khong_co_ngay() -> None:
    assert make_game(release_dates=[]).release_year is None


def test_release_year_bo_qua_ngay_rac() -> None:
    game = make_game(release_dates=[ReleaseDate(region="ww", date="TBA")])
    assert game.release_year is None


# --- to_mongo -------------------------------------------------------------


def test_to_mongo_giu_parent_game_la_objectid() -> None:
    """Để dạng chuỗi thì không join ngược về game cha được."""
    parent = ObjectId()
    doc = make_game(type="dlc", parent_game=parent).to_mongo()
    assert doc["parent_game"] == parent
    assert isinstance(doc["parent_game"], ObjectId)


def test_to_mongo_ghi_ngay_dang_chuoi() -> None:
    doc = make_game().to_mongo()
    assert doc["release_dates"][0]["date"] == "2022-02-25"


def test_parent_game_nhan_chuoi_24_ky_tu() -> None:
    parent = ObjectId()
    assert make_game(parent_game=str(parent)).parent_game == parent


def test_parent_game_tu_choi_chuoi_rac() -> None:
    with pytest.raises(ValidationError):
        make_game(parent_game="không-phải-objectid")


# --- ràng buộc kiểu -------------------------------------------------------


def test_type_chi_nhan_bon_gia_tri() -> None:
    with pytest.raises(ValidationError):
        make_game(type="mod")
