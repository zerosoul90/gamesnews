"""Test normalize_vi. PHASE-1.md yêu cầu tối thiểu 20 case, gồm tên có dấu,
tên Nhật, số La Mã và dấu hai chấm."""

from __future__ import annotations

import pytest

from app.services.normalize import (
    build_aliases,
    build_aliases_normalized,
    collapse_spaces,
    normalize_vi,
    roman_to_arabic,
    strip_latin_diacritics,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # --- cơ bản ---
        ("Elden Ring", "elden ring"),
        ("ELDEN RING", "elden ring"),
        ("  Elden   Ring  ", "elden ring"),
        ("", ""),
        ("   ", ""),
        # --- dấu hai chấm và dấu câu ---
        ("The Witcher 3: Wild Hunt", "the witcher 3 wild hunt"),
        ("Half-Life 2", "half life 2"),
        ("Marvel's Spider-Man", "marvels spider man"),
        ("Assassin's Creed", "assassins creed"),
        (
            "Ori and the Blind Forest (Definitive Edition)",
            "ori and the blind forest definitive edition",
        ),
        ("Rick & Morty", "rick morty"),
        ("S.T.A.L.K.E.R. 2", "s t a l k e r 2"),
        # --- số La Mã: giữ nguyên, không tự đổi sang số Ả Rập ---
        ("Final Fantasy VII", "final fantasy vii"),
        ("Grand Theft Auto V", "grand theft auto v"),
        ("Civilization VI", "civilization vi"),
        ("Diablo II: Resurrected", "diablo ii resurrected"),
        # --- tiếng Việt có dấu ---
        ("Đế Chế", "de che"),
        ("Liên Quân Mobile", "lien quan mobile"),
        ("Võ Lâm Truyền Kỳ", "vo lam truyen ky"),
        ("Đột Kích", "dot kich"),
        ("Thiên Long Bát Bộ", "thien long bat bo"),
        ("Nhẫn Giả Đường Phố", "nhan gia duong pho"),
        # --- ngôn ngữ khác: dấu là một phần của chữ, không được bỏ ---
        ("エルデンリング", "エルデンリング"),
        ("ゼルダの伝説", "ゼルダの伝説"),
        ("原神", "原神"),
        ("배틀그라운드", "배틀그라운드"),
        ("Pokémon Légendes", "pokemon legendes"),
        ("Brütal Legend", "brutal legend"),
        ("Café Rouge", "cafe rouge"),
        # --- biến thể hiển thị ---
        ("ＥＬＤＥＮ　ＲＩＮＧ", "elden ring"),  # Latin fullwidth
        ("ｴﾙﾃﾞﾝﾘﾝｸﾞ", "エルデンリング"),  # katakana nửa chiều rộng
        # --- emoji, ký hiệu ---
        ("Untitled Goose Game 🦆", "untitled goose game"),
        ("Cyberpunk 2077™", "cyberpunk 2077"),
        ("Ni no Kuni II™: Revenant Kingdom", "ni no kuni ii revenant kingdom"),
    ],
)
def test_normalize_vi(raw: str, expected: str) -> None:
    assert normalize_vi(raw) == expected


def test_dakuten_khong_bi_bo() -> None:
    """Bẫy dễ sập nhất: NFD tách デ thành テ + dakuten. Bỏ hết dấu tổ hợp là
    đổi luôn nghĩa của chữ Nhật."""
    assert normalize_vi("エルデンリング") == "エルデンリング"
    assert "テ" not in normalize_vi("エルデンリング")
    # ガ (ga) không được biến thành カ (ka)
    assert normalize_vi("ガンダム") == "ガンダム"


def test_chu_d_gach_ngang() -> None:
    """đ không phải d có dấu — NFD không tách được, phải thay tay."""
    assert strip_latin_diacritics("đ") == "đ"  # NFD một mình không xử lý được
    assert normalize_vi("đ") == "d"
    assert normalize_vi("Đế Chế") == "de che"


def test_idempotent() -> None:
    """Chuẩn hoá hai lần phải ra cùng kết quả, nếu không thì job đồng bộ chạy
    lại sẽ sinh diff giả."""
    for raw in ("Đế Chế", "The Witcher 3: Wild Hunt", "エルデンリング", "Pokémon"):
        once = normalize_vi(raw)
        assert normalize_vi(once) == once


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Elden Ring", "eldenring"),
        ("Liên Quân Mobile", "lienquanmobile"),
        ("The Witcher 3: Wild Hunt", "thewitcher3wildhunt"),
        ("PUBG", "pubg"),
    ],
)
def test_collapse_spaces(raw: str, expected: str) -> None:
    assert collapse_spaces(raw) == expected


def test_build_aliases_giu_thu_tu_va_khong_trung() -> None:
    aliases = build_aliases(
        {"primary": "Elden Ring", "vi": "Elden Ring", "ja": "エルデンリング"},
        ["ELDEN RING", "Elden Ring"],
    )
    # "Elden Ring" chỉ xuất hiện một lần dù có ở cả titles.vi lẫn alt names.
    assert aliases == ["Elden Ring", "エルデンリング", "ELDEN RING"]


def test_build_aliases_bo_gia_tri_rong() -> None:
    assert build_aliases({"primary": "Halo", "vi": "", "ja": "   "}) == ["Halo"]


def test_build_aliases_normalized_co_ca_ban_lien_va_ban_cach() -> None:
    normalized = build_aliases_normalized(["Elden Ring", "エルデンリング"])
    assert "elden ring" in normalized
    assert "eldenring" in normalized
    assert "エルデンリング" in normalized


def test_build_aliases_normalized_khong_trung() -> None:
    # "PUBG" cho ra bản cách và bản liền giống hệt nhau -> chỉ giữ một.
    assert build_aliases_normalized(["PUBG", "pubg"]) == ["pubg"]


def test_chuoi_alias_tu_titles_toi_normalized() -> None:
    """Đường đi thật: titles -> aliases -> aliases_normalized."""
    aliases = build_aliases(
        {"primary": "Đế Chế", "en": "Age of Empires"},
        ["AoE"],
    )
    normalized = build_aliases_normalized(aliases)

    assert "de che" in normalized
    assert "deche" in normalized
    assert "age of empires" in normalized
    assert "aoe" in normalized


# ---------------------------------------------------------- số La Mã


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("final fantasy vii", "final fantasy 7"),
        ("civilization vi", "civilization 6"),
        ("diablo ii resurrected", "diablo 2 resurrected"),
        ("grand theft auto iv", "grand theft auto 4"),
        ("final fantasy xiv", "final fantasy 14"),
        ("ni no kuni ii revenant kingdom", "ni no kuni 2 revenant kingdom"),
        ("dynasty warriors ix", "dynasty warriors 9"),
        # Ký tự đơn: V và X được đổi.
        ("final fantasy x", "final fantasy 10"),
        ("grand theft auto v", "grand theft auto 5"),
        ("dragon quest v", "dragon quest 5"),
    ],
)
def test_roman_to_arabic(raw: str, expected: str) -> None:
    assert roman_to_arabic(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "half life 2",  # đã là số Ả Rập
        "elden ring",  # không có số La Mã
        "vi",  # một từ duy nhất -> giữ nguyên là chữ
        "xi",
        "x",
        # Ngoài khoảng 2-40: mi/di/li/mc là từ thật, không được coi là số.
        "mi casa",
        "di sản",
        "mc donald",
        "li kỳ",
        # I là 1, dưới sàn 2 -> đại từ "I" trong tiếng Anh vẫn an toàn.
        "i am fish",
        "we are i",
    ],
)
def test_roman_to_arabic_khong_doi(raw: str) -> None:
    assert roman_to_arabic(normalize_vi(raw)) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Cái giá của việc cho phép ký tự đơn: X dùng như chữ cái cũng bị đổi.
        # Đây là alias thừa, không thay alias gốc, nên chấp nhận được.
        ("mega man x", "mega man 10"),
        ("project x", "project 10"),
    ],
)
def test_ky_tu_don_sinh_alias_thua_da_biet(raw: str, expected: str) -> None:
    assert roman_to_arabic(raw) == expected


@pytest.mark.parametrize("token", ["iiii", "vv", "xxxx", "ic", "im", "vx"])
def test_so_la_ma_viet_sai_thi_bo_qua(token: str) -> None:
    """Chỉ nhận dạng viết chuẩn: 4 là "iv", không phải "iiii"."""
    assert roman_to_arabic(f"game {token}") is None


def test_alias_so_la_ma_vao_aliases_normalized() -> None:
    normalized = build_aliases_normalized(["Final Fantasy VII"])

    assert "final fantasy vii" in normalized  # bản gốc vẫn còn
    assert "final fantasy 7" in normalized
    assert "finalfantasy7" in normalized  # kèm bản viết liền
    assert "finalfantasyvii" in normalized


def test_alias_so_la_ma_khong_dong_toi_ten_khong_co_so() -> None:
    normalized = build_aliases_normalized(["Elden Ring", "Liên Quân Mobile"])
    assert not any(char.isdigit() for char in " ".join(normalized))


def test_alias_ky_tu_don() -> None:
    normalized = build_aliases_normalized(["Final Fantasy X"])
    assert "final fantasy x" in normalized  # bản gốc vẫn còn
    assert "final fantasy 10" in normalized
