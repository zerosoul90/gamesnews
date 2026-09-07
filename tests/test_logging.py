from __future__ import annotations

import json
import logging

from app.core.logging import JsonFormatter, request_id_var


def render(record: logging.LogRecord) -> dict[str, object]:
    payload: dict[str, object] = json.loads(JsonFormatter().format(record))
    return payload


def make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="gọi nguồn ngoài", args=None, exc_info=None,
    )
    record.__dict__.update(extra)
    return record


def test_log_ra_json_hop_le() -> None:
    payload = render(make_record())
    assert payload["level"] == "INFO"
    assert payload["message"] == "gọi nguồn ngoài"  # không escape tiếng Việt
    assert payload["logger"] == "test"


def test_field_them_qua_extra_duoc_giu() -> None:
    payload = render(make_record(source="steam", cost=4))
    assert payload["source"] == "steam"
    assert payload["cost"] == 4


def test_co_request_id_khi_dang_trong_request() -> None:
    token = request_id_var.set("req-1")
    try:
        payload = render(make_record())
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "req-1"


def test_khong_co_request_id_khi_ngoai_request() -> None:
    assert "request_id" not in render(make_record())
