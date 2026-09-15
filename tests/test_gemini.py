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
from app.adapters.llm.gemini import EMBED_DIM, HTTP_TIMEOUT_SECONDS, GeminiAdapter


def adapter_with(
    handler: Any, *, api_key: str = "khoa-gia", limiter: Any = None
) -> tuple[GeminiAdapter, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiAdapter(http, api_key, limiter), http


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


# --- Giãn nhịp -------------------------------------------------------------
#
# Trần đo tay 2026-09-13: `generateContent` 20/phút, `batchEmbedContents` ~100
# content/phút. Bắn hết tốc rồi ăn 429 thì vẫn tốn đúng ngần ấy lượt gọi, chỉ
# khác là không lượt nào trả về gì — 46/50 ở lượt crawl đầu tiên.


class FakeLimiter:
    """Ghi lại từng lần xin token. Không cần Redis — `RateLimiter` là Protocol."""

    def __init__(self) -> None:
        self.acquired: list[int] = []

    async def acquire(self, tokens: int = 1) -> None:
        self.acquired.append(tokens)


async def test_embed_tinh_cost_bang_so_content() -> None:
    """Chốt đắt nhất của cả file.

    Google tính MỖI CONTENT là một request dù chúng đi chung một lời gọi HTTP —
    chính API nói ra điều đó khi từ chối lô 120: "at most 100 requests can be in
    one batch". Đặt cost=1 ở đây thì bucket đếm thiếu 25 lần và cái trần trở
    thành đồ trang trí.
    """
    limiter = FakeLimiter()
    adapter, http = adapter_with(
        reply({"embeddings": [{"values": [0.1] * EMBED_DIM} for _ in range(25)]}),
        limiter=limiter,
    )

    await adapter.embed([f"game {i}" for i in range(25)])
    await http.aclose()

    assert limiter.acquired == [25]


async def test_tom_tat_tinh_cost_bang_mot() -> None:
    limiter = FakeLimiter()
    adapter, http = adapter_with(
        reply(gemini_text('{"translated_title":"a","summary_vi":"b"}')), limiter=limiter
    )

    await adapter.summarize_and_translate(title="x", content="y")
    await http.aclose()

    assert limiter.acquired == [1]


async def test_xin_token_truoc_khi_goi_mang() -> None:
    """Xin sau khi gọi thì token đã tiêu rồi, giãn nhịp thành vô nghĩa."""
    thu_tu: list[str] = []

    class GhiThuTu(FakeLimiter):
        async def acquire(self, tokens: int = 1) -> None:
            thu_tu.append("token")
            await super().acquire(tokens)

    def handler(request: httpx.Request) -> httpx.Response:
        thu_tu.append("http")
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * EMBED_DIM}]})

    adapter, http = adapter_with(handler, limiter=GhiThuTu())
    await adapter.embed(["Elden Ring"])
    await http.aclose()

    assert thu_tu == ["token", "http"]


async def test_lo_qua_tran_cua_api_thi_bao_ngay() -> None:
    """API từ chối lô > 100 bằng 400. Để nó tự ném thì lỗi hiện ở tận tầng HTTP,
    còn người gọi mất cả lô mà không biết vì sao."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("không được gọi API với lô quá trần")

    adapter, http = adapter_with(handler)
    with pytest.raises(PermanentError, match="100"):
        await adapter.embed([f"game {i}" for i in range(101)])
    await http.aclose()


async def test_khong_co_limiter_thi_van_goi_duoc() -> None:
    """Đoạn đo tay và test không phải dựng Redis mới gọi được adapter."""
    adapter, http = adapter_with(reply({"embeddings": [{"values": [0.1] * EMBED_DIM}]}))

    assert len(await adapter.embed(["Elden Ring"])) == 1
    await http.aclose()


async def test_embed_khai_so_chieu_va_dung_model_con_song() -> None:
    """Hai thứ đều hỏng lặng lẽ nếu sai.

    `text-embedding-004` đã bị Google gỡ hẳn (kiểm tay 2026-09-12: 404), nên tên
    model phải là cái còn sống. Và `gemini-embedding-001` mặc định trả **3072**
    chiều — quên `outputDimensionality` thì Gemini vẫn trả 200, chỉ tới lúc
    Qdrant nhận lô mới từ chối vì collection dựng ở 768.
    """
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * EMBED_DIM}]})

    adapter, http = adapter_with(handler)
    await adapter.embed(["Elden Ring"])
    await http.aclose()

    assert "text-embedding-004" not in seen["url"]
    assert seen["body"]["requests"][0]["outputDimensionality"] == EMBED_DIM


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


def test_burst_cua_bucket_khong_duoc_vuot_tran_mot_phut() -> None:
    """Điều kiện đúng là `2 * capacity <= trần`, không phải `capacity <= 80% trần`.

    `capacity` vừa là nhịp vừa là **burst**: bucket đầy cho đi `capacity` lời gọi
    tức thì, rồi refill thêm `capacity` lời nữa trong cùng 60 giây — tối đa ~2C
    rơi vào MỘT cửa sổ của Google. Đo 2026-09-15: đặt capacity 4 trên trần 5 thì
    7 lời gọi lọt trong 36 giây rồi 429, đúng như 2C dự đoán, dù 4 vẫn là "80%
    của 5".
    """
    from app.adapters.llm.gemini import GENERATE_CEILING_PER_MINUTE, GENERATE_RATE

    assert GENERATE_RATE.per_seconds == 60.0, "phép tính 2C chỉ đúng khi cửa sổ là một phút"
    assert 2 * GENERATE_RATE.capacity <= GENERATE_CEILING_PER_MINUTE


def _loi_quota(quota_id: str, tran: str) -> dict[str, Any]:
    return {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "message": "You exceeded your current quota, please check your plan and billing.",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            # Giống hệt nhau ở CẢ HAI chiều — nên nó không nói
                            # được gì về đơn vị của cái trần.
                            "quotaMetric": (
                                "generativelanguage.googleapis.com/generate_content_free_tier_requests"
                            ),
                            "quotaId": quota_id,
                            "quotaValue": tran,
                        }
                    ],
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"},
            ],
        }
    }


@pytest.mark.parametrize(
    ("quota_id", "tran"),
    [
        ("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "20"),
        ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "15"),
    ],
)
async def test_429_noi_ro_tran_theo_ngay_hay_theo_phut(quota_id: str, tran: str) -> None:
    """Thân 429 phải mang được ĐƠN VỊ của cái trần, không chỉ con số.

    Đây là chốt cho một lỗi đã tốn nguyên một lượt làm: ngày 2026-09-13 thân lỗi
    chỉ in `quotaMetric` — chuỗi giống hệt nhau ở cả chiều phút lẫn chiều ngày —
    nên `trần=20` bị đọc thành 20/phút. Nó là 20/NGÀY, và bốn hằng số trần mỗi
    lượt của hai job tin tức đều đã suy sai từ đó.

    Một con số không có đơn vị thì chưa phải số đo. Chiều nằm trong `quotaId`,
    nên `quotaId` phải có mặt trong thông báo.
    """
    adapter, http = adapter_with(reply(_loi_quota(quota_id, tran), status=429))
    with pytest.raises(TransientError) as bat:
        await adapter.summarize_and_translate(title="t", content="c")
    thong_bao = str(bat.value)

    assert quota_id in thong_bao, "thiếu quotaId thì không biết trần là theo phút hay theo ngày"
    assert f"trần={tran}" in thong_bao
    await http.aclose()


async def test_tran_cho_rong_hon_doi_cham_cua_google() -> None:
    """Lời gọi phải mang trần chờ RIÊNG của adapter, không để httpx mặc định.

    Độ trễ của model bình thường ~1,4 giây, nhưng đo 2026-09-15 gặp đợt chậm
    phía Google làm cùng một prompt tầm thường mất 24-31 giây — ngay trên ranh
    giới trần cũ là 30. Vượt trần không phải "chậm một lượt" mà là **mất bài**:
    `_post` ném `TransientError` và job dừng lượt.
    """
    ghi: dict[str, Any] = {}

    def bat(request: httpx.Request) -> httpx.Response:
        ghi["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, json=gemini_text('{"a": 1}'))

    adapter, http = adapter_with(bat)
    await adapter.summarize_and_translate(title="t", content="c")
    await http.aclose()

    # httpx tách trần thành bốn pha; `timeout=<số>` đặt cả bốn bằng nhau.
    assert ghi["timeout"]["read"] == HTTP_TIMEOUT_SECONDS
    assert HTTP_TIMEOUT_SECONDS > 31, "phải rộng hơn đợt chậm đã đo được"
