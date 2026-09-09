import difflib
import logging
import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.services.normalize import normalize_vi

logger = logging.getLogger(__name__)


# --- TẦNG 1: EXACT MATCH ---
def exact_match_from_url(content: str) -> str | None:
    """Tầng 1: Tìm link Steam/Epic trong nội dung bài viết.
    Trả về steam_appid hoặc epic_slug nếu tìm thấy.
    """
    # Tìm Steam AppID (VD: store.steampowered.com/app/1245620)
    steam_match = re.search(r"steampowered\.com/app/(\d+)", content)
    if steam_match:
        return f"steam:{steam_match.group(1)}"

    # Tìm Epic Slug (VD: store.epicgames.com/p/alan-wake-2)
    epic_match = re.search(r'epicgames\.com/[^/]+/p/([^/?"\']+)', content)
    if epic_match:
        return f"epic:{epic_match.group(1)}"

    return None


# --- TẦNG 2: FUZZY MATCH ---
def fuzzy_match_aliases(title: str, aliases: list[str]) -> tuple[str | None, float]:
    """Tầng 2: So sánh tiêu đề/từ khoá với danh sách aliases.
    Trả về (matched_alias, score). Ngưỡng tin cậy >= 0.85.
    """
    normalized_title = normalize_vi(title)
    if not normalized_title:
        return None, 0.0

    best_match = None
    best_score = 0.0

    for alias in aliases:
        # Sử dụng difflib để tính tỉ lệ giống nhau (0.0 đến 1.0)
        score = difflib.SequenceMatcher(None, normalized_title, alias).ratio()
        if score > best_score:
            best_score = score
            best_match = alias

    if best_score >= 0.85:
        return best_match, best_score

    return None, best_score


# --- TẦNG 3: EMBEDDING MATCH ---
# Tầng này sẽ bắn text qua LLM để lấy Vector (Ví dụ: nomic-embed-text)
# Sau đó query vào Qdrant để lấy Entity gần nhất.
# Hiện tại tôi sẽ định nghĩa interface chờ sẵn.
async def embedding_match(content: str, qdrant_client: Any) -> tuple[str | None, float]:
    """Tầng 3: Tìm kiếm ngữ nghĩa bằng Vector Database."""
    # TODO: Implement Qdrant search
    # return game_id, confidence_score (0.0 - 1.0)
    return None, 0.0


async def match_entity(
    db: AsyncIOMotorDatabase[dict[str, Any]],
    article_title: str,
    article_content: str,
    qdrant_client: Any,
) -> tuple[str | None, str, float]:
    """
    Luồng xử lý 3 tầng:
    Trả về (game_id, matching_tier, confidence_score)
    """
    # 1. Exact Match
    exact_id = exact_match_from_url(article_content)
    if exact_id:
        # Nếu tìm thấy steam_appid, truy vấn DB để lấy `game_id`
        # MOCK: Tạm thời trả về trực tiếp để test logic
        logger.info(f"Tầng 1 (Exact Match) thành công: {exact_id}")
        return exact_id, "exact", 1.0

    # 2. Fuzzy Match
    # Trong thực tế, chúng ta sẽ kéo các aliases phổ biến lên cache, hoặc truy vấn Text Search
    # MOCK DATA để test
    mock_aliases = ["elden ring", "hắc thần thoại ngộ không", "black myth wukong", "cyberpunk 2077"]
    matched_alias, score = fuzzy_match_aliases(article_title, mock_aliases)

    if matched_alias and score >= 0.85:
        logger.info(f"Tầng 2 (Fuzzy Match) thành công: {matched_alias} (Score: {score:.2f})")
        # Truy vấn CSDL để lấy ID thật từ alias
        return f"mock_game_id_{matched_alias.replace(' ', '_')}", "fuzzy", score

    # 3. Embedding Match
    embed_id, embed_score = await embedding_match(article_content, qdrant_client)
    if embed_id and embed_score >= 0.70:  # Ngưỡng embedding thấp hơn vì nó tìm ngữ nghĩa
        logger.info(f"Tầng 3 (Embedding) thành công: {embed_id} (Score: {embed_score:.2f})")
        return embed_id, "embedding", embed_score

    logger.warning("Không thể match entity. Chuyển vào Hàng Đợi Duyệt Tay (Manual Review).")
    return None, "manual", 0.0
