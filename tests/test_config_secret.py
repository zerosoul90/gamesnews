"""`jwt_secret` mặc định không được phép sống sót ra khỏi máy dev.

Giá trị mặc định nằm ngay trong mã nguồn và nó ký session token của người dùng
(`services/auth.py`). Deploy mà quên đặt biến này thì bất kỳ ai đọc repo cũng ký
được token hợp lệ cho bất kỳ tài khoản nào — và không có triệu chứng nào cho
tới lúc đã bị lợi dụng.

Test đi qua biến môi trường, đúng đường mà cấu hình thật đi. `_env_file=None` là
bắt buộc: máy dev có `.env` thật, đọc phải nó thì kết quả phụ thuộc vào nội dung
file đó chứ không phải vào code.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_JWT_SECRET, Settings


@pytest.mark.parametrize("app_env", ["staging", "prod"])
def test_secret_mac_dinh_bi_chan_ngoai_dev(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    """Chặn cả staging: đó cũng là máy thật, có dữ liệu thật, mở ra mạng."""
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("JWT_SECRET", DEFAULT_JWT_SECRET)

    with pytest.raises(ValidationError) as loi:
        Settings(_env_file=None)

    assert "JWT_SECRET" in str(loi.value)


def test_dev_van_chay_duoc_voi_secret_mac_dinh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Máy dev không phải đặt biến này mới chạy được — bắt đặt thì mỗi lần
    clone repo lại vướng một bước không giúp gì cho an toàn."""
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    settings = Settings(_env_file=None)

    assert settings.jwt_secret.get_secret_value() == DEFAULT_JWT_SECRET


@pytest.mark.parametrize("app_env", ["staging", "prod"])
def test_secret_rieng_thi_chay_duoc(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("JWT_SECRET", "mot-gia-tri-rieng-du-dai")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret.get_secret_value() != DEFAULT_JWT_SECRET
