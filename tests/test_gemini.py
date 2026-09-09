"""Adapter Gemini — `app/adapters/llm/gemini.py`.

Không gọi ra Internet: `httpx.MockTransport` chặn ngay ở tầng vận chuyển, nên
test kiểm đúng thứ ta viết (dựng payload, bóc kết quả, phân loại lỗi) chứ không
kiểm mạng của người chạy test.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.adapters.base import PermanentError, TransientError
from app.adapters.llm.gemini import EMBED_DIM, GeminiAdapter


def adapter_with(
    handler: Any, *, api_key: str = "khoa-gia"
) -> tuple[GeminiAdapter, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiAdapter(http, api_key), http


def reply(payload: dict[str, Any], status: int = 200) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def gemini_text(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


async def test_thieu_key_thi_bao_chua_cau_hinh() -> None:
    adapter, http = adapter_with(reply({}), api_key="")
    assert adapter.configured is False
    with pytest.raises(PermanentError, match="chưa được cấu hình"):
        await adapter.summarize_and_translate(title="x", content="y")
    await http.aclose()


async def test_key_di_trong_header_khong_di_trong_query() -> None:
    """Key trong query string nằm lại trong log của mọi proxy trên đường đi."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["header"] = request.headers.get("x-goog-api-key")
        return httpx.Response(200, json=gemini_text('{"translated_title":"a","summary_vi":"b"}'))

    adapter, http = adapter_with(handler, api_key="bi-mat")
    await adapter.summarize_and_translate(title="x", content="y")
    await http.aclose()

    assert seen["header"] == "bi-mat"
    assert "bi-mat" not in seen["url"]


async def test_doc_duoc_json_co_cau_truc() -> None:
    body = gemini_text(
        json.dumps(
            {
                "translated_title": "Elden Ring ra bản mở rộng",
                "summary_vi": "Tóm tắt.",
                "suggested_alias": "Elden Ring",
            }
        )
    )
    adapter, http = adapter_with(reply(body))
    parsed = await adapter.summarize_and_translate(title="Elden Ring DLC", content="...")
    await http.aclose()

    assert parsed is not None
    assert parsed.translated_title == "Elden Ring ra bản mở rộng"
    assert parsed.suggested_alias == "Elden Ring"


async def test_json_hong_thi_tra_none_chu_khong_no() -> None:
    """Model trả rác là chuyện thường; nó không được làm chết cả lượt crawl."""
    adapter, http = adapter_with(reply(gemini_text("đây không phải JSON")))
    assert await adapter.summarize_and_translate(title="x", content="y") is None
    await http.aclose()


async def test_khong_co_candidate_thi_tra_none() -> None:
    adapter, http = adapter_with(reply({"candidates": []}))
    assert await adapter.summarize_and_translate(title="x", content="y") is None
    await http.aclose()


async def test_yeu_cau_response_mime_type_json() -> None:
    """Thiếu cờ này thì model bọc JSON trong ```json và json.loads chết ngay."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=gemini_text('{"translated_title":"a","summary_vi":"b"}'))

    adapter, http = adapter_with(handler)
    await adapter.summarize_and_translate(title="x", content="y")
    await http.aclose()

    assert seen["body"]["generationConfig"]["response_mime_type"] == "application/json"


async def test_cat_bot_noi_dung_qua_dai() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=gemini_text('{"translated_title":"a","summary_vi":"b"}'))

    adapter, http = adapter_with(handler)
    await adapter.summarize_and_translate(title="x", content="z" * 50_000)
    await http.aclose()

    prompt = seen["body"]["contents"][0]["parts"][0]["text"]
    assert len(prompt) < 20_000


async def test_embed_giu_dung_thu_tu_va_so_luong() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        count = len(json.loads(request.content)["requests"])
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [float(i)] * EMBED_DIM} for i in range(count)]},
        )

    adapter, http = adapter_with(handler)
    vectors = await adapter.embed(["a", "b", "c"])
    await http.aclose()

    assert len(vectors) == 3
    assert vectors[0][0] == 0.0
    assert vectors[2][0] == 2.0


async def test_embed_lech_so_luong_thi_no_chu_khong_ghep_bua() -> None:
    """Ghép nhầm vector với game là gắn sai entity vĩnh viễn, im lặng."""
    adapter, http = adapter_with(reply({"embeddings": [{"values": [0.1] * EMBED_DIM}]}))
    with pytest.raises(PermanentError, match="vector"):
        await adapter.embed(["a", "b"])
    await http.aclose()


async def test_embed_rong_khong_goi_mang() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("không được gọi API cho danh sách rỗng")

    adapter, http = adapter_with(handler)
    assert await adapter.embed([]) == []
    await http.aclose()


async def test_429_la_loi_tam_thoi_500_cung_vay() -> None:
    """Lý do bỏ SDK: phải phân biệt được lỗi chờ-rồi-thử-lại với lỗi vô vọng."""
    adapter, http = adapter_with(reply({}, status=429))
    with pytest.raises(TransientError):
        await adapter.embed(["a"])
    await http.aclose()


async def test_400_la_loi_vinh_vien() -> None:
    adapter, http = adapter_with(reply({}, status=400))
    with pytest.raises(PermanentError):
        await adapter.embed(["a"])
    await http.aclose()
