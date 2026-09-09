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

from app.adapters.base import PermanentError, TransientError, classify_http_status

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

TEXT_MODEL = "gemini-2.5-flash"
# 768 chiều. Đổi model là phải nạp lại toàn bộ vector trong Qdrant, vì vector
# của hai model khác nhau không so sánh được với nhau.
EMBED_MODEL = "text-embedding-004"
EMBED_DIM = 768

# Cắt bớt thân bài trước khi gửi. Bài tin dài hàng chục nghìn ký tự không làm
# bản tóm tắt tốt hơn, chỉ làm hoá đơn dài ra.
MAX_CONTENT_CHARS = 8000

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


class LLMParsedArticle(BaseModel):
    """Kết quả sau khi LLM đọc một bài."""

    translated_title: str = Field(description="Tiêu đề đã dịch sang tiếng Việt.")
    summary_vi: str = Field(description="Tóm tắt tiếng Việt, 2-3 câu.")
    suggested_alias: str | None = Field(
        default=None, description="Tên gốc của game trong bài, null nếu không chắc."
    )


class GeminiAdapter:
    """Nói chuyện với Gemini. Không biết gì về Mongo hay về nghiệp vụ tin tức."""

    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        """Có key hay không. Người gọi phải tự kiểm và tự quyết định làm gì tiếp.

        Không tự trả None khi thiếu key rồi để tầng trên đoán: "chưa cấu hình"
        và "gọi rồi nhưng không ra gì" là hai chuyện khác nhau, và chỉ có một
        trong hai là lỗi vận hành cần ai đó đi sửa.
        """
        return bool(self._api_key)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise PermanentError("GEMINI_API_KEY chưa được cấu hình")

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
            raise error(f"{path} -> {response.status_code}: {response.text[:200]}")

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PermanentError(f"Gemini trả về không phải JSON: {exc}") from exc
        return body

    async def summarize_and_translate(
        self, *, title: str, content: str
    ) -> LLMParsedArticle | None:
        """Dịch tiêu đề, tóm tắt, và đoán tên game — trong một lần gọi.

        Trả None khi model trả về thứ không đọc được. Ném `AdapterError` khi
        gọi hỏng: hai chuyện đó khác nhau, và job phía trên xử lý khác nhau.
        """
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": PROMPT.format(
                                title=title, content=content[:MAX_CONTENT_CHARS]
                            )
                        }
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

        Gộp lô bằng `batchEmbedContents`: nạp vector cho cả catalog mà gọi từng
        cái một thì số request bằng số game.
        """
        if not texts:
            return []

        payload = {
            "requests": [
                {
                    "model": f"models/{EMBED_MODEL}",
                    "content": {"parts": [{"text": text}]},
                }
                for text in texts
            ]
        }
        data = await self._post(f"models/{EMBED_MODEL}:batchEmbedContents", payload)

        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise PermanentError(
                f"Gemini trả {len(embeddings)} vector cho {len(texts)} đoạn văn bản"
            )
        return [[float(value) for value in item.get("values") or []] for item in embeddings]
