"""Adapter mẫu: nguồn trả JSON, chuẩn hoá về một model pydantic."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any, ClassVar

from pydantic import BaseModel

from app.adapters.base import AdapterConfig, BaseAdapter, PermanentError

# Một "phản hồi" trong kịch bản: hoặc payload thô, hoặc lỗi để ném ra.
Scripted = dict[str, Any] | Exception


class DummyPayload(BaseModel):
    """Model nội bộ. Nguồn thật sẽ chuẩn hoá về model trong `app/models/`."""

    external_id: str
    title: str


class DummyAdapter(BaseAdapter[dict[str, Any], DummyPayload]):
    source: ClassVar[str] = "dummy"

    def __init__(self, config: AdapterConfig, script: Iterable[Scripted]) -> None:
        super().__init__(config)
        self._script: deque[Scripted] = deque(script)
        self.calls = 0

    async def fetch_raw(self, **params: Any) -> dict[str, Any]:
        self.calls += 1
        if not self._script:
            raise PermanentError("kịch bản dummy đã hết")
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    def normalize(self, raw: dict[str, Any]) -> DummyPayload:
        try:
            return DummyPayload(external_id=str(raw["id"]), title=str(raw["name"]))
        except KeyError as exc:
            # Payload thiếu trường là lỗi vĩnh viễn — gọi lại vẫn thiếu.
            raise PermanentError(f"payload dummy thiếu trường {exc}") from exc
