import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
)


class LLMParsedArticle(BaseModel):
    translated_title: str = Field(
        description="Tiêu đề bài viết được dịch sang tiếng Việt một cách tự nhiên."
    )
    summary_vi: str = Field(
        description="Tóm tắt nội dung bài viết bằng tiếng Việt, ngắn gọn trong khoảng 2-3 câu."
    )
    suggested_alias: str | None = Field(
        default=None,
        description=(
            "Tên gốc của game được nhắc đến trong bài viết (tiếng Anh hoặc "
            "tiếng Việt). Để null nếu không chắc chắn hoặc không đề cập tới "
            "game cụ thể."
        ),
    )


async def summarize_and_translate(
    http_client: Any, original_content: str, original_title: str
) -> LLMParsedArticle | None:
    """Gọi Gemini API qua REST để dịch tiêu đề, tóm tắt và trích xuất tên game (nếu có)."""
    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value()

    if not api_key:
        logger.warning("gemini_api_key chưa được cấu hình. Bỏ qua bước tóm tắt bằng LLM.")
        return None

    # Prompt yêu cầu trả về JSON chuẩn
    prompt = f"""
    Bạn là một trợ lý ảo chuyên dịch và tóm tắt tin tức về game.
    Hãy đọc bài viết dưới đây và thực hiện các bước sau:
    1. Dịch tiêu đề sang tiếng Việt một cách mượt mà và hấp dẫn.
    2. Tóm tắt nội dung bài viết bằng tiếng Việt trong khoảng 2-3 câu ngắn gọn.
    3. Xác định tên gốc của trò chơi (game) được nhắc đến nhiều nhất trong
       bài viết. Nếu bài viết nói chung chung hoặc không nhắc đến game cụ thể
       nào, hãy để null.

    Bắt buộc trả về kết quả dưới định dạng JSON theo đúng schema sau, không
    thêm bất kỳ văn bản nào khác ngoài JSON:
    {{
        "translated_title": "Tiêu đề tiếng Việt",
        "summary_vi": "Nội dung tóm tắt tiếng Việt",
        "suggested_alias": "Tên game gốc hoặc null"
    }}

    --- TIÊU ĐỀ GỐC ---
    {original_title}

    --- NỘI DUNG BÀI VIẾT ---
    {original_content}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.3},
    }

    try:
        # http_client là một httpx.AsyncClient được truyền từ context/worker
        response = await http_client.post(
            f"{GEMINI_API_URL}?key={api_key}", json=payload, timeout=15.0
        )
        response.raise_for_status()

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            logger.error("Gemini không trả về kết quả hợp lệ.")
            return None

        text_response = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

        # Đọc chuỗi JSON và ép kiểu vào BaseModel
        parsed_json = json.loads(text_response)
        result = LLMParsedArticle(**parsed_json)
        return result

    except Exception as e:
        logger.error(f"Lỗi khi gọi Gemini API: {e}")
        return None
