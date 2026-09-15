"""Adapter Gemini — tóm tắt, dịch, và sinh vector. `docs/PHASE-6.md`.

Gộp lại từ ba chỗ từng cùng nói chuyện với Gemini bằng ba cách khác nhau:
`services/llm.py` (httpx, `gemini-1.5-flash`, trả JSON có cấu trúc),
`adapters/llm/gemini.py` (SDK `google-genai`, `gemini-2.5-flash`, trả văn bản
thô) và `adapters/llm/embedding.py` (SDK, embedding). Không cái nào được gọi từ
đâu cả, nên ba bản cùng tồn tại mà không ai thấy — tới lúc đấu dây thật thì
phải chọn một.

Chọn httpx, bỏ SDK, vì cùng lý do mọi adapter khác trong dự án dùng httpx:
`classify_http_status` phân biệt lỗi tạm thời với lỗi vĩnh viễn, và cơ chế
retry/token bucket của `adapters/base.py` chỉ hiểu được lỗi ở dạng đó. Đi qua
SDK thì mọi lỗi trở thành `APIError` và tầng trên hết đường phân loại — 429
(chờ rồi thử lại) trông y hệt 400 (thử lại bao nhiêu lần cũng thế).

**Một lần gọi lấy cả ba thứ.** Dịch tiêu đề, tóm tắt và đoán tên game là ba
việc trên cùng một bài; tách thành ba request thì trả tiền ba lần cho cùng một
đoạn nội dung đầu vào.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.adapters.base import (
    PermanentError,
    RateLimit,
    RateLimiter,
    TransientError,
    classify_http_status,
)

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Hạn mức free tier tính RIÊNG cho từng model (`quotaId` là
# `...PerProjectPerModel-FreeTier`), nên chọn model CHÍNH LÀ chọn trần — và
# `gemini-2.5-flash` chỉ còn **20 lời gọi/ngày**, đo 2026-09-15. Ở trần đó job
# dịch tin không chạy được: riêng 671 bài tồn đã là hơn ba mươi năm, chưa kể
# tin mới mỗi ngày cũng đã vượt. Không cách chia nào cứu được một con số như thế.
#
# `gemini-3.5-flash-lite` đo được **15 lời gọi/phút** và không chạm chiều ngày
# trong cả phiên đo — đủ rộng để job có nghĩa trở lại.
#
# Không dùng `gemini-2.5-flash-lite`: Google trả 404 "no longer available to new
# users" và tự chỉ sang bản 3.5 này. Cũng không dùng alias `-latest`: nó đổi
# model dưới chân mình, mà đổi model là đổi cả trần lẫn giọng văn bản dịch.
TEXT_MODEL = "gemini-3.5-flash-lite"
# Đổi model là phải nạp lại toàn bộ vector trong Qdrant, vì vector của hai model
# khác nhau không so sánh được với nhau.
#
# `text-embedding-004` đã bị Google GỠ HẲN: `ListModels` không còn liệt kê nó và
# mọi lời gọi trả 404 "is not found for API version v1beta". Kiểm tay 2026-09-12
# với key thật. Ba model embedding còn sống là `gemini-embedding-001` (GA),
# `gemini-embedding-2` và bản preview của nó.
EMBED_MODEL = "gemini-embedding-001"
# Mặc định của `gemini-embedding-001` là 3072 chiều, nhưng nó nhận
# `outputDimensionality`. Giữ 768 để **không phải nạp lại collection Qdrant
# đang có** — và vì Qdrant ở đây dùng COSINE, chuyện Google không chuẩn hoá sẵn
# vector ở số chiều rút gọn không ảnh hưởng tới thứ hạng.
EMBED_DIM = 768

# Cắt bớt thân bài trước khi gửi. Bài tin dài hàng chục nghìn ký tự không làm
# bản tóm tắt tốt hơn, chỉ làm hoá đơn dài ra.
MAX_CONTENT_CHARS = 8000

# --- Hạn mức, đo tay 2026-09-15 với key free -------------------------------
#
# Hai quota TÁCH BIỆT, nên hai bucket tách biệt. Gộp chung thì việc dịch tin và
# việc nạp vector ăn lẫn hạn mức của nhau mà không cần thiết.
#
# MỖI model lại có HAI chiều hạn mức, và chúng dùng CHUNG một `quotaMetric`
# (`generate_content_free_tier_requests`). Chiều chỉ nằm trong `quotaId`:
#
#   GenerateRequestsPerMinutePerProjectPerModel-FreeTier  -> 15 (flash-lite 3.5)
#   GenerateRequestsPerDayPerProjectPerModel-FreeTier     -> 20 (flash 2.5)
#
# Đây là cái bẫy đã ăn trọn một lượt làm: ngày 2026-09-13 `trần=20` bị đọc thành
# 20/**phút** và bốn hằng số trần của hai job tin tức đều suy ra từ đó. Nó là
# 20/**ngày**. Đọc nhầm được vì `_describe_error` khi ấy in `quotaMetric` — thứ
# giống hệt nhau ở cả hai chiều — và bỏ mất `quotaId`. Nay nó in `quotaId`.
#
# Bài học đắt hơn con số: một cái trần không có ĐƠN VỊ thì chưa phải số đo. Và
# hạn mức bên thứ ba là thứ đo lại được, không phải hằng số chép một lần rồi tin
# mãi — chỗ nào suy ra từ nó phải nói rõ, để lần sau còn tìm thấy mà sửa theo.
#
# Vì sao capacity là 7 chứ không phải 12 (=80% của 15): **capacity vừa là nhịp
# vừa là burst**. Bucket đầy cho đi C lời gọi tức thì rồi refill C lời nữa trong
# cùng 60 giây, tức tối đa ~2C lọt vào MỘT cửa sổ của Google. Đo được đúng thế:
# đặt capacity 4 thì 7 lời gọi lọt trong 36 giây rồi 429. Nên điều kiện là
# 2C ≤ trần, không phải C ≤ 80% trần: 2x7 = 14 ≤ 15.
#
# "Chừa 20%" của bản trước là cách nghĩ sai — nó chỉnh nhịp mà không chạm vào
# burst, mà chính burst mới là thứ vượt cửa sổ.
#
# Trần đo được để thành HẰNG SỐ RIÊNG, không nằm trong chú thích: có test chốt
# `2 * capacity <= trần`, nên lần sau ai nới capacity sẽ thấy đỏ ngay thay vì
# thấy 429 sau nửa ngày chạy.
GENERATE_CEILING_PER_MINUTE = 15
GENERATE_RATE = RateLimit(capacity=7, per_seconds=60.0)

# Embedding có **HAI** hạn mức, và chỉ một trong hai thuộc về bucket này:
#
# - theo phút: đo được ~100 content mới trôi (lượt đầu qua đúng 100 rồi 429,
#   lượt sau qua 50 rồi 429). Đây là cái `EMBED_RATE` canh.
# - theo ngày: `trần=1000` trong thân lỗi. Tới lúc cạn thì **kể cả lô một
#   content cũng bị từ chối** và `retryDelay` đếm ngược về mốc cửa sổ — token
#   bucket không đỡ được, vì nó chỉ biết nhịp. Cái đó do
#   `jobs/embeddings.MAX_TEXTS_PER_RUN` canh.
#
# Nhầm hai thứ này là bẫy: bucket "đúng luật" suốt mà nửa ngày sau vẫn 429 hết.
EMBED_RATE = RateLimit(capacity=80, per_seconds=60.0)

# Trần cứng của chính API, không phải hạn mức nhịp: gửi 120 thì trả **400**
# `at most 100 requests can be in one batch`. Chính câu đó cũng xác nhận mô
# hình tính phí — mỗi content là một "request", không phải mỗi lời gọi HTTP.
MAX_EMBED_BATCH = 100

PROMPT = """\
Bạn là trợ lý biên tập tin game cho độc giả Việt Nam.

Đọc bài dưới đây rồi trả về JSON đúng schema sau, không kèm bất kỳ chữ nào khác:

{{
  "translated_title": "tiêu đề dịch sang tiếng Việt, tự nhiên, giữ đúng nghĩa",
  "summary_vi": "tóm tắt tiếng Việt trong 2-3 câu",
  "suggested_alias": "tên gốc của game được nhắc tới nhiều nhất, hoặc null"
}}

Quy tắc cho "suggested_alias": chỉ điền TÊN GAME, không điền cả câu tiêu đề.
Bài nói chuyện chung chung, nói về công ty, hay về phần cứng thì để null.

--- TIÊU ĐỀ GỐC ---
{title}

--- NỘI DUNG ---
{content}
"""


def _describe_error(response: httpx.Response) -> str:
    """Mô tả gọn một phản hồi lỗi, GIỮ LẠI phần nói về quota.

    Bản trước cắt thân lỗi ở `response.text[:200]`, mà 200 ký tự đầu của một
    lỗi Google chỉ là câu mẫu "You exceeded your current quota, please check
    your plan and billing details" — vô dụng. Thứ cần đọc nằm trong
    `error.details[].QuotaFailure`: **quota nào** và **trần bao nhiêu**. Không
    có nó thì lúc dính 429 phải đi dò tay xem hạn mức là theo phút hay theo
    ngày, đúng việc đã phải làm ngày 2026-09-13.

    Và bản trước vẫn KHÔNG trả lời được đúng câu hỏi đó, dù docstring hứa: nó in
    `quotaMetric`, mà trường này giống hệt nhau ở cả hai chiều
    (`...generate_content_free_tier_requests` cho cả phút lẫn ngày). Chiều nằm
    trong `quotaId` — `GenerateRequestsPerDayPerProjectPerModel-FreeTier` so với
    bản `PerMinute...` — đúng cái trường bị `or` bỏ qua khi `quotaMetric` có
    mặt, tức là luôn luôn.

    Cái giá đã trả: ngày 2026-09-13 `trần=20` bị đọc thành 20/phút và bốn hằng
    số trần của hai job tin tức đều suy ra từ đó. Nó là 20/**ngày**. Ưu tiên
    `quotaId` vì nó mang cả tên lẫn chiều; `quotaMetric` chỉ là bản dự phòng.
    """
    try:
        err = response.json().get("error") or {}
    except ValueError:
        return response.text[:200]

    phan: list[str] = [str(err.get("status") or response.status_code)]
    for detail in err.get("details") or []:
        kind = str(detail.get("@type", ""))
        if kind.endswith("QuotaFailure"):
            for vi_pham in detail.get("violations") or []:
                metric = vi_pham.get("quotaId") or vi_pham.get("quotaMetric") or "?"
                phan.append(f"quota={metric} trần={vi_pham.get('quotaValue', '?')}")
        elif kind.endswith("RetryInfo") and detail.get("retryDelay"):
            phan.append(f"thử lại sau {detail['retryDelay']}")

    if len(phan) == 1:
        # Không phải lỗi quota — giữ câu mô tả của Google.
        phan.append(str(err.get("message", ""))[:200])
    return " | ".join(p for p in phan if p)


class LLMParsedArticle(BaseModel):
    """Kết quả sau khi LLM đọc một bài."""

    translated_title: str = Field(description="Tiêu đề đã dịch sang tiếng Việt.")
    summary_vi: str = Field(description="Tóm tắt tiếng Việt, 2-3 câu.")
    suggested_alias: str | None = Field(
        default=None, description="Tên gốc của game trong bài, null nếu không chắc."
    )


class GeminiAdapter:
    """Nói chuyện với Gemini. Không biết gì về Mongo hay về nghiệp vụ tin tức."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._http = http
        self._api_key = api_key
        # `None` nghĩa là không giãn nhịp — chỉ dùng trong test và trong những
        # đoạn đo tay. Job chạy thật LUÔN phải truyền bucket vào; hai hằng số
        # `GENERATE_RATE` / `EMBED_RATE` ngay dưới đây nói vì sao.
        self._limiter = limiter

    @property
    def configured(self) -> bool:
        """Có key hay không. Người gọi phải tự kiểm và tự quyết định làm gì tiếp.

        Không tự trả None khi thiếu key rồi để tầng trên đoán: "chưa cấu hình"
        và "gọi rồi nhưng không ra gì" là hai chuyện khác nhau, và chỉ có một
        trong hai là lỗi vận hành cần ai đó đi sửa.
        """
        return bool(self._api_key)

    async def _post(self, path: str, payload: dict[str, Any], *, cost: int = 1) -> dict[str, Any]:
        if not self._api_key:
            raise PermanentError("GEMINI_API_KEY chưa được cấu hình")

        # Giãn nhịp TRƯỚC khi gọi, không phải sau khi ăn 429. Bắn hết tốc rồi
        # nhận 429 thì vẫn tốn đúng ngần ấy lượt gọi, chỉ khác là không lượt nào
        # trả về gì — đo được ở lượt crawl đầu: 46/50 lời gọi hỏng.
        #
        # `cost` chứ không phải 1: `batchEmbedContents` gửi 25 content trong một
        # lời gọi HTTP thì Google tính **25 request**, không phải một. Đặt cost=1
        # ở đây là bucket đếm thiếu 25 lần và trần trở thành trang trí.
        if self._limiter is not None:
            await self._limiter.acquire(cost)

        url = f"{API_ROOT}/{path}"
        try:
            response = await self._http.post(
                url,
                json=payload,
                # Key đi trong header, KHÔNG trong query string: query string
                # nằm lại trong log của mọi proxy trên đường đi.
                headers={"x-goog-api-key": self._api_key},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise TransientError(f"Không gọi được Gemini: {exc!r}") from exc

        error = classify_http_status(response.status_code)
        if error is not None:
            raise error(f"{path} -> {response.status_code}: {_describe_error(response)}")

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PermanentError(f"Gemini trả về không phải JSON: {exc}") from exc
        return body

    async def summarize_and_translate(self, *, title: str, content: str) -> LLMParsedArticle | None:
        """Dịch tiêu đề, tóm tắt, và đoán tên game — trong một lần gọi.

        Trả None khi model trả về thứ không đọc được. Ném `AdapterError` khi
        gọi hỏng: hai chuyện đó khác nhau, và job phía trên xử lý khác nhau.
        """
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT.format(title=title, content=content[:MAX_CONTENT_CHARS])}
                    ]
                }
            ],
            "generationConfig": {
                # Ép model trả JSON. Thiếu dòng này thì nó hay bọc JSON trong
                # ```json ... ``` và `json.loads` chết ở ký tự đầu tiên.
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        }

        data = await self._post(f"models/{TEXT_MODEL}:generateContent", payload)

        candidates = data.get("candidates") or []
        if not candidates:
            logger.warning("Gemini không trả candidate nào", extra={"title": title[:120]})
            return None

        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(str(part.get("text") or "") for part in parts)
        if not text.strip():
            return None

        try:
            return LLMParsedArticle(**json.loads(text))
        except (ValueError, ValidationError) as exc:
            logger.warning(
                "không đọc được JSON của Gemini",
                extra={"error": str(exc), "raw": text[:200]},
            )
            return None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Sinh vector cho một lô văn bản. Giữ nguyên thứ tự đầu vào.

        Gộp lô bằng `batchEmbedContents` để tiết kiệm **vòng mạng**, không phải
        quota: Google tính mỗi content là một request dù chúng đi chung một lời
        gọi HTTP. Vì vậy `cost` truyền xuống bucket là `len(texts)`.
        """
        if not texts:
            return []
        if len(texts) > MAX_EMBED_BATCH:
            # Trần cứng của API. Để nó tự ném 400 thì lỗi hiện ra ở tận tầng
            # HTTP, còn người gọi thì mất cả lô mà không biết vì sao.
            raise PermanentError(
                f"batchEmbedContents nhận tối đa {MAX_EMBED_BATCH} đoạn, được đưa {len(texts)}"
            )

        payload = {
            "requests": [
                {
                    "model": f"models/{EMBED_MODEL}",
                    "content": {"parts": [{"text": text}]},
                    # Bắt buộc khai: thiếu nó thì `gemini-embedding-001` trả 3072
                    # chiều, và Qdrant từ chối cả lô vì collection dựng ở 768.
                    "outputDimensionality": EMBED_DIM,
                }
                for text in texts
            ]
        }
        data = await self._post(
            f"models/{EMBED_MODEL}:batchEmbedContents", payload, cost=len(texts)
        )

        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise PermanentError(
                f"Gemini trả {len(embeddings)} vector cho {len(texts)} đoạn văn bản"
            )
        return [[float(value) for value in item.get("values") or []] for item in embeddings]
