"""Chuẩn hoá tên game để khớp entity.

`SCHEMA.md`: entity game chuẩn hoá là phần khó nhất của dự án, sai ở đây thì
mọi thứ phía sau đều hỏng. Hàm trong file này quyết định hai tên có được coi
là một game hay không, nên mọi thay đổi phải kèm test.

Ràng buộc quan trọng nhất: **chỉ bỏ dấu của chữ Latin**. Tiếng Nhật cũng dùng
dấu tổ hợp (dakuten) nhưng ở đó dấu là một phần của chữ, không phải trang trí:
デ mà bỏ dấu thành テ là đổi hẳn chữ. Checkpoint `エルデンリング` ra đúng game
sẽ đỏ ngay nếu chỗ này làm ẩu.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping

# Chữ đ/Đ không phải chữ d có dấu — Unicode coi nó là một chữ cái riêng, NFD
# không tách ra được. Phải thay tay.
_DJ_MAP = str.maketrans({"đ": "d", "Đ": "D"})

# Dấu nháy nằm giữa chữ thì bỏ hẳn, không thay bằng khoảng trắng:
# "Assassin's Creed" phải ra "assassins creed", không phải "assassin s creed".
_INTRA_WORD = frozenset("'’ʼ`´")

# Phải bỏ TRƯỚC bước NFKC: NFKC đổi ™ thành hai chữ cái "TM", sau đó bộ lọc
# ký tự đặc biệt không thấy gì lạ và "Cyberpunk 2077™" ra "cyberpunk 2077tm".
# Tên game trên Steam đầy ™ và ®.
_TRADEMARK = str.maketrans("", "", "™®©℠")


def _is_latin(char: str) -> bool:
    try:
        return "LATIN" in unicodedata.name(char)
    except ValueError:  # ký tự không có tên trong bảng Unicode
        return False


def strip_latin_diacritics(text: str) -> str:
    """Bỏ dấu của chữ Latin, giữ nguyên dấu của mọi hệ chữ khác."""
    decomposed = unicodedata.normalize("NFD", text)

    out: list[str] = []
    base_is_latin = False
    for char in decomposed:
        if unicodedata.category(char) == "Mn":
            # Dấu tổ hợp: chỉ bỏ khi nó đang gắn vào một chữ Latin.
            if not base_is_latin:
                out.append(char)
            continue
        base_is_latin = _is_latin(char)
        out.append(char)

    # Ghép lại để dấu của tiếng Nhật trở về dạng chữ đơn (テ + ゙ -> デ).
    return unicodedata.normalize("NFC", "".join(out))


def normalize_vi(text: str) -> str:
    """Đưa một tên về dạng dùng để so khớp.

    Lowercase, bỏ dấu Latin (đ -> d), bỏ ký tự đặc biệt, gộp khoảng trắng.
    Chữ Nhật/Trung/Hàn được giữ nguyên — chúng là nội dung, không phải rác.
    """
    text = text.translate(_TRADEMARK)
    # NFKC gộp các biến thể hiển thị: chữ Latin fullwidth, katakana nửa chiều
    # rộng... về một dạng duy nhất trước khi so.
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DJ_MAP)
    text = strip_latin_diacritics(text)
    text = text.lower()

    out: list[str] = []
    for char in text:
        if char in _INTRA_WORD:
            continue
        category = unicodedata.category(char)
        # Giữ chữ cái (L*) và chữ số (N*); mọi thứ còn lại thành khoảng trắng.
        out.append(char if category[0] in ("L", "N") else " ")

    return " ".join("".join(out).split())


def collapse_spaces(text: str) -> str:
    """Biến thể viết liền: 'elden ring' -> 'eldenring'.

    Người Việt gõ tên game rất hay dính chữ, và tên thương mại nhiều khi cũng
    viết liền (RimWorld, PUBG). Đây là alias riêng, không thay cho bản có
    khoảng trắng.
    """
    return normalize_vi(text).replace(" ", "")


def build_aliases(
    titles: Mapping[str, str],
    alternative_names: Iterable[str] = (),
) -> list[str]:
    """Gom alias thô từ tên các ngôn ngữ và alternative names của IGDB.

    Giữ nguyên chữ gốc (còn dấu, còn hoa thường) — `aliases` là để hiển thị và
    để duyệt tay; bản dùng so khớp là `aliases_normalized`.

    Thứ tự ổn định và không trùng, để chạy lại job đồng bộ không sinh diff giả.
    """
    seen: dict[str, None] = {}

    primary = titles.get("primary", "")
    for value in (primary, *(v for k, v in titles.items() if k != "primary"), *alternative_names):
        cleaned = " ".join(value.split())
        if cleaned and cleaned not in seen:
            seen[cleaned] = None

    return list(seen)


def build_aliases_normalized(aliases: Iterable[str]) -> list[str]:
    """Sinh `aliases_normalized` từ `aliases`: bản bỏ dấu + bản viết liền."""
    seen: dict[str, None] = {}

    for alias in aliases:
        for variant in (normalize_vi(alias), collapse_spaces(alias)):
            if variant and variant not in seen:
                seen[variant] = None

    return list(seen)
