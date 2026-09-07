"""Log dạng JSON, mỗi dòng một object, luôn kèm request id nếu có."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

# Đặt bởi middleware ở tầng API, hoặc bởi worker khi bắt đầu mỗi job.
# ContextVar nên an toàn giữa các task async chạy song song.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Thuộc tính có sẵn của LogRecord — mọi thứ ngoài danh sách này là field do
# người gọi thêm vào qua `extra=` và sẽ được đưa thẳng vào JSON.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def new_request_id() -> str:
    return uuid.uuid4().hex


def setup_logging(level: str = "INFO") -> None:
    """Gắn JsonFormatter vào root logger. Gọi một lần lúc khởi động."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn tự cấu hình logger riêng; ép chúng đi qua root để định dạng
    # đồng nhất, nếu không access log sẽ ra text lẫn với JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
