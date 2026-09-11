"""Parse `pc_requirements` của Steam — `app/adapters/steam/adapter.py`.

`SystemRequirements` có trong model từ đầu nhưng `to_game` chưa bao giờ điền,
nên mọi game trong catalog đều có `system_requirements` rỗng và section "Yêu cầu
cấu hình" trên trang game luôn bị ẩn.

Fixture là payload thật ghi lại 2026-09-11, không phải HTML tôi tự viết: chính
vì đi lấy dữ liệu thật mà mới thấy Steam trả **ba** hình dạng khác nhau cho cùng
một field, trong đó hình dạng thứ ba làm parser chỉ tìm `<li>` mất sạch dữ liệu
mà không báo gì.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from app.adapters.steam.adapter import _requirement_spec, _system_requirements, to_game

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REQS = json.loads((FIXTURES / "steam_pc_requirements.json").read_text(encoding="utf-8"))

ELDEN_RING = REQS["1245620"]
TROPICO_4 = REQS["57690"]
DARK_MESSIAH = REQS["2130"]
WALLPAPER_ENGINE = REQS["431960"]


def spec_of(entry: dict[str, Any], level: str = "minimum") -> dict[str, str]:
    return _requirement_spec(entry["pc_requirements"].get(level))


def test_parse_duoc_cac_truong_chinh() -> None:
    spec = spec_of(ELDEN_RING)

    assert spec["OS"] == "Windows 10"
    assert spec["Processor"] == "INTEL CORE I5-8400 or AMD RYZEN 3 3300X"
    assert spec["Memory"] == "12 GB RAM"
    assert spec["Storage"] == "60 GB available space"


def test_tieu_de_minimum_khong_thanh_mot_truong() -> None:
    """Steam đặt `<strong>Minimum:</strong>` NGOÀI thẻ `<ul>` làm tiêu đề. Parse
    cả thẻ `<strong>` của cả chuỗi thay vì chỉ trong `<li>` thì sinh ra một
    trường tên "Minimum" với giá trị là toàn bộ phần còn lại."""
    spec = spec_of(ELDEN_RING)

    assert "Minimum" not in spec
    assert not any("Minimum" in key for key in spec)


def test_dong_khong_co_khoa_khong_bi_mat() -> None:
    """`<li>Requires a 64-bit processor and operating system</li>` không có
    `<strong>` nào. Bỏ qua những dòng như vậy là lặng lẽ đánh rơi thông tin."""
    spec = spec_of(ELDEN_RING)

    assert "Requires a 64-bit processor" in spec["Additional Notes"]


def test_khoa_rong_gia_tri_bi_bo() -> None:
    """Steam gửi `<strong>Additional Notes:</strong>` với value rỗng ở rất nhiều
    game. Một khoá không giá trị chỉ là một dòng trống trong bảng cấu hình."""
    # Trong payload Elden Ring, "Additional Notes" của Steam là rỗng; giá trị duy
    # nhất nằm ở khoá này phải tới từ dòng không khoá.
    spec = spec_of(ELDEN_RING)

    assert spec["Additional Notes"].strip()
    assert all(value.strip() for value in spec.values())


def test_khoa_duoc_chuan_hoa_bo_dau_sao_va_ky_hieu() -> None:
    """Tropico 4 viết `OS *:` và `DirectX®:`, Elden Ring viết `OS:` và
    `DirectX:`. Cùng một trường, hai khoá — giao diện sẽ hiện hai dòng cho một
    thứ, và không cách nào tra cứu theo tên trường."""
    tropico = spec_of(TROPICO_4)
    elden = spec_of(ELDEN_RING)

    assert "OS" in tropico and "OS *" not in tropico
    assert "DirectX" in tropico and "DirectX®" not in tropico
    # Cùng tên khoá giữa hai game là điểm chính của phép chuẩn hoá này.
    assert {"OS", "DirectX"} <= set(tropico) & set(elden)


def test_gia_tri_giu_nguyen_ky_hieu_thuong_mai() -> None:
    """Chỉ chuẩn hoá KHOÁ. `AMD Athlon™` trong giá trị là tên sản phẩm."""
    spec = spec_of(DARK_MESSIAH)

    assert "Athlon™" in spec["Additional Notes"]


def test_tab_thut_le_bi_gom_lai() -> None:
    """Tropico 4 trả `Vista` sau một chuỗi tab dùng để thụt lề HTML. Không gom
    thì tab đi thẳng vào giao diện."""
    spec = spec_of(TROPICO_4)

    assert spec["OS"] == "Windows XP SP3 (32-bit), Vista / 7 (32 or 64-bit)"
    assert all("\t" not in value and "\n" not in value for value in spec.values())


def test_chuoi_phang_khong_co_li_van_giu_duoc_noi_dung() -> None:
    """Chốt chính.

    Dark Messiah (appid 2130) trả `<strong>Minimum:</strong> AMD Athlon, 512MB
    RAM, ...` — không một thẻ `<li>` nào, và nhồi cả phần Recommended vào đúng
    field `minimum`. Parser chỉ tìm `<li>` trả về `{}`: section cấu hình biến
    mất và không có gì cho biết là đã mất.
    """
    spec = spec_of(DARK_MESSIAH)

    assert spec, "hình dạng chuỗi phẳng bị mất sạch"
    notes = spec["Additional Notes"]
    assert "512MB RAM" in notes
    assert "7GB HDD Space" in notes
    # Steam nhồi cả hai mức vào field `minimum`, nên cả hai chữ đều còn đây.
    assert "Minimum:" in notes and "Recommended:" in notes


def test_thieu_muc_recommended_thi_rong_chu_khong_loi() -> None:
    """Payload Dark Messiah không có khoá `recommended` nào."""
    assert "recommended" not in DARK_MESSIAH["pc_requirements"]

    reqs = _system_requirements({"pc_requirements": DARK_MESSIAH["pc_requirements"]})

    assert reqs.recommended == {}
    assert reqs.minimum  # mức tối thiểu vẫn đọc được


def test_field_la_list_rong_thi_tra_ve_rong() -> None:
    """Steam trả `[]` thay vì dict khi hoàn toàn không có yêu cầu — thấy rõ ở
    `mac_requirements` của game chỉ có bản PC. `.get("minimum")` trên một list
    là AttributeError, tức job đồng bộ chết giữa chừng."""
    assert WALLPAPER_ENGINE["mac_requirements"] == []

    reqs = _system_requirements({"pc_requirements": WALLPAPER_ENGINE["mac_requirements"]})

    assert reqs.minimum == {}
    assert reqs.recommended == {}


def test_thieu_han_field_thi_tra_ve_rong() -> None:
    reqs = _system_requirements({})

    assert reqs.minimum == {}
    assert reqs.recommended == {}


def test_to_game_dien_system_requirements() -> None:
    """Khoá luôn việc `to_game` có thật sự gọi parser: trước lượt này nó bỏ hẳn
    field, nên parser viết đúng đến đâu cũng không tới được database."""
    game = to_game(
        {
            "type": "game",
            "steam_appid": 1245620,
            "name": "ELDEN RING",
            "pc_requirements": ELDEN_RING["pc_requirements"],
        }
    )

    assert game is not None
    assert game.system_requirements.minimum["OS"] == "Windows 10"
    assert game.system_requirements.recommended["Memory"] == "16 GB RAM"
