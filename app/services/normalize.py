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


# --- số La Mã ---------------------------------------------------------
#
# "Final Fantasy VII" và "final fantasy 7" phải ra cùng một game. Sinh thêm
# alias dạng số Ả Rập, KHÔNG thay alias gốc.
#
# Chỗ này dễ sinh rác nên có hai chốt chặn:
#
# 1. Chỉ nhận giá trị 2-40, tức là khoảng số phần tiếp theo có thật của game.
#    Chốt này gánh phần lớn công việc: MI (1001), DI (501), LI (51), MC (1100)
#    tự bị loại — chúng là từ thật trong tiếng Việt và tiếng Anh. Ký tự đơn
#    cũng chỉ còn V (5) và X (10) lọt qua, vì I là 1 (dưới sàn) còn
#    L/C/D/M là 50/100/500/1000 (trên trần).
# 2. Tên chỉ có đúng một từ thì không đổi, để "VI", "XI", "X" đứng một mình
#    được giữ nguyên là chữ.
#
# Ký tự đơn ĐƯỢC đổi theo yêu cầu: "Final Fantasy X" -> "final fantasy 10",
# "Grand Theft Auto V" -> "grand theft auto 5". Cái giá phải trả là các tên
# dùng X như chữ cái cũng bị sinh alias sai: "Mega Man X" có thêm alias
# "mega man 10". Đây là alias thừa, không thay alias gốc.
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
_ROMAN_MAX = 40


def _roman_to_int(token: str) -> int | None:
    """Trả về giá trị nếu `token` là số La Mã viết đúng chuẩn, không thì None.

    Bắt buộc đúng dạng chuẩn tắc: "iiii" và "vv" bị loại vì số 4 chỉ có một
    cách viết đúng là "iv".
    """
    total = 0
    previous = 0
    for char in reversed(token):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += value if value >= previous else -value
        previous = max(previous, value)

    if not 1 <= total <= 3999:
        return None
    # Viết ngược lại rồi so — cách rẻ nhất để loại các dạng viết sai.
    return total if _int_to_roman(total) == token else None


def _int_to_roman(value: int) -> str:
    pairs = (
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    )
    out: list[str] = []
    for amount, symbol in pairs:
        count, value = divmod(value, amount)
        out.append(symbol * count)
    return "".join(out)


def roman_to_arabic(normalized: str) -> str | None:
    """Đổi mọi token số La Mã trong một tên ĐÃ chuẩn hoá sang số Ả Rập.

    Trả về None nếu không có gì để đổi.
    """
    tokens = normalized.split()
    if len(tokens) < 2:  # chốt 2: tên một từ thì giữ nguyên
        return None

    changed = False
    out: list[str] = []
    for token in tokens:
        value = _roman_to_int(token)
        if value is not None and 2 <= value <= _ROMAN_MAX:  # chốt 1
            out.append(str(value))
            changed = True
        else:
            out.append(token)

    return " ".join(out) if changed else None


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
    """Sinh `aliases_normalized`: bản bỏ dấu, bản viết liền, bản số Ả Rập."""
    seen: dict[str, None] = {}

    def add(value: str) -> None:
        if value and value not in seen:
            seen[value] = None

    for alias in aliases:
        base = normalize_vi(alias)
        add(base)
        add(base.replace(" ", ""))

        arabic = roman_to_arabic(base)
        if arabic is not None:
            add(arabic)
            add(arabic.replace(" ", ""))

    return list(seen)
