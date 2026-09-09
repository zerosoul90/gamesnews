"""Gắn bài viết vào entity game — `docs/PHASE-6.md` mục 3.

Tài liệu gọi đây là "phần khó nhất và là nơi hệ thống dễ hỏng nhất", và đặt ra
một nguyên tắc chi phối mọi ngưỡng trong file này:

> **thà bỏ sót còn hơn gắn sai.**

Lý do: bài bị bỏ sót thì nằm trong hàng đợi duyệt tay, ai cũng thấy và sửa
được trong mười giây. Bài bị gắn nhầm thì hiển thị lặng lẽ dưới trang một game
khác, không ai báo, và còn kéo theo chỉ số hot của Phase 7 sai theo.

Ba tầng, tin cậy giảm dần:

1. **Exact** — có link store trong bài, tra ngược ra entity. Chắc chắn nhất.
2. **Alias** — một cụm từ trong tiêu đề trùng khít một alias đã chuẩn hoá.
3. **Embedding** — vector tên game trong Qdrant (`services/embeddings.py`).

Không tầng nào đủ tin cậy thì trả `manual`, và người gọi có nghĩa vụ đẩy bài
vào `entity_review_queue` (xem `services/entity_review.py`). Không đoán bừa.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from qdrant_client import AsyncQdrantClient

from app.adapters.base import AdapterError
from app.adapters.llm.gemini import GeminiAdapter
from app.services import embeddings
from app.services.catalog import find_game_by_external_id, games
from app.services.normalize import normalize_vi

logger = logging.getLogger(__name__)

Db = AsyncIOMotorDatabase[dict[str, Any]]

MatchTier = Literal["exact", "alias", "embedding", "manual"]

# Cụm dài nhất đem đi dò alias. Tên game dài nhất trong catalog cũng hiếm khi
# quá 8 từ, mà mỗi từ thêm vào là một cụm nữa phải sinh.
MAX_ALIAS_WORDS = 8

# Alias một từ chỉ được tin khi nó đủ dài. Không có chốt này thì những alias
# như "go", "control", "journey", "the" khớp vào bất kỳ tiêu đề nào và gắn sai
# hàng loạt — đúng kiểu hỏng mà nguyên tắc trên muốn tránh.
MIN_SINGLE_WORD_CHARS = 8

# Khớp alias là khớp CHÍNH XÁC trên chuỗi đã chuẩn hoá, nên độ tin cậy cao;
# nhưng vẫn dưới 1.0 để tầng exact luôn thắng khi cả hai cùng khớp.
ALIAS_CONFIDENCE = 0.95

# Ngưỡng cosine của tầng 3.
#
# 0.82 là con số **khởi điểm, chưa đo trên dữ liệu thật** — và phải nói thẳng ra
# thay vì để nó trông như một hằng số đã hiệu chỉnh. Cách hiệu chỉnh đúng: chạy
# một đợt tin thật, đọc `entity_review_queue` (bỏ sót) và đối chiếu các bài đã
# gắn ở tầng embedding (gắn sai), rồi kéo ngưỡng theo nguyên tắc đầu file —
# thà bỏ sót còn hơn gắn sai, tức là **nghi ngờ thì kéo LÊN**.
EMBEDDING_THRESHOLD = 0.82

# Khoảng cách tối thiểu giữa ứng viên nhất và nhì. Sát nhau thì vector không
# phân biệt được hai entity, và chọn bừa là gắn sai 50% số lần.
EMBEDDING_MARGIN = 0.03


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """Kết quả gắn entity.

    `matched_on` giữ lại thứ đã làm nên kết quả — link store hoặc alias. Nó là
    thứ người duyệt tay cần thấy để biết vì sao hệ thống đoán như vậy, và cũng
    là thứ đi vào log khi phải truy ngược một lần gắn sai.
    """

    game_id: ObjectId | None
    tier: MatchTier
    confidence: float
    matched_on: str | None = None

    @property
    def matched(self) -> bool:
        return self.game_id is not None


NO_MATCH = EntityMatch(game_id=None, tier="manual", confidence=0.0)


# --- Tầng 1: link store trong nội dung bài ---------------------------------

# Mỗi mẫu bắt đúng một nguồn trong `external_ids`. Thứ tự trong dict là thứ tự
# ưu tiên khi một bài có nhiều link.
_STORE_PATTERNS: dict[str, re.Pattern[str]] = {
    "steam_appid": re.compile(r"store\.steampowered\.com/app/(\d+)"),
    "app_store": re.compile(r"apps\.apple\.com/[^\s\"']*?/id(\d+)"),
    "google_play": re.compile(r"play\.google\.com/store/apps/details\?id=([\w.]+)"),
    "epic_slug": re.compile(r"epicgames\.com/[^\s\"']*?/p/([\w-]+)"),
}


def store_links(content: str) -> list[tuple[str, str]]:
    """Mọi link store tìm thấy, dạng (tên field trong external_ids, giá trị)."""
    found: list[tuple[str, str]] = []
    for field, pattern in _STORE_PATTERNS.items():
        for match in pattern.finditer(content):
            pair = (field, match.group(1))
            if pair not in found:
                found.append(pair)
    return found


async def match_by_store_link(db: Db, content: str) -> EntityMatch | None:
    """Tầng 1. None nghĩa là không có link, hoặc có mà không tra ra entity.

    Link tra không ra entity là **lỗ hổng catalog**, không phải lỗi bài viết:
    game đó có thật trên store mà ta chưa nạp về. Ghi log riêng để còn đếm
    được, rồi để bài rơi xuống tầng sau.
    """
    for field, raw in store_links(content):
        value: str | int = int(raw) if field == "steam_appid" else raw
        doc = await find_game_by_external_id(db, field, value)
        if doc is not None:
            return EntityMatch(
                game_id=doc["_id"],
                tier="exact",
                confidence=1.0,
                matched_on=f"{field}={raw}",
            )
        logger.info(
            "link store không tra ra entity — thiếu game trong catalog",
            extra={"source": field, "value": raw},
        )
    return None


# --- Tầng 2: alias ---------------------------------------------------------


def ngrams(normalized: str, max_words: int = MAX_ALIAS_WORDS) -> list[str]:
    """Mọi cụm từ liên tiếp trong một chuỗi đã chuẩn hoá, dài trước ngắn sau.

    Dài trước để cụm cụ thể hơn được xét trước: tiêu đề chứa "elden ring
    nightreign" phải ra bản Nightreign, không phải Elden Ring gốc.
    """
    words = normalized.split()
    out: list[str] = []
    for size in range(min(max_words, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            out.append(" ".join(words[start : start + size]))
    return out


def is_specific_enough(alias: str) -> bool:
    """Alias có đủ đặc trưng để tin hay không.

    Một từ ngắn thì gần như chắc chắn là từ thông thường lọt vào danh sách
    alias, không phải tên game.
    """
    return len(alias.split()) >= 2 or len(alias) >= MIN_SINGLE_WORD_CHARS


async def match_by_alias(db: Db, title: str) -> EntityMatch | None:
    """Tầng 2: một cụm trong tiêu đề trùng khít một alias đã chuẩn hoá.

    Trùng khít chứ không phải "gần giống": `normalize_vi` đã lo phần bỏ dấu,
    thường hoá và bỏ ký tự đặc biệt — tức phần lớn khác biệt thật giữa cách
    viết. Thêm một tầng đo độ giống chuỗi lên trên đó chỉ mở đường cho gắn sai,
    mà chỗ để sửa những ca đó là vòng phản hồi alias ở `entity_review.py`.

    Hai game cùng khớp một cụm dài như nhau thì **không chọn cái nào**: đó
    đúng là lúc con người cần nhìn vào.
    """
    normalized = normalize_vi(title)
    if not normalized:
        return None

    candidates = [gram for gram in ngrams(normalized) if is_specific_enough(gram)]
    if not candidates:
        return None

    # Một truy vấn duy nhất cho mọi cụm; `aliases_normalized` là index multikey
    # nên đây là index scan, không phải quét bảng.
    cursor = games(db).find(
        {"aliases_normalized": {"$in": candidates}},
        {"aliases_normalized": 1, "slug": 1},
    )

    best_len = 0
    best: list[tuple[ObjectId, str]] = []
    async for doc in cursor:
        aliases = set(doc.get("aliases_normalized") or [])
        for gram in candidates:
            if gram not in aliases:
                continue
            length = len(gram.split())
            if length > best_len:
                best_len, best = length, [(doc["_id"], gram)]
            elif length == best_len and doc["_id"] not in [x for x, _ in best]:
                best.append((doc["_id"], gram))
            break

    if not best:
        return None

    if len(best) > 1:
        logger.info(
            "nhiều game cùng khớp một cụm, chuyển duyệt tay",
            extra={"title": title[:120], "matches": len(best)},
        )
        return None

    game_id, alias = best[0]
    return EntityMatch(
        game_id=game_id, tier="alias", confidence=ALIAS_CONFIDENCE, matched_on=alias
    )


# --- Tầng 3: embedding -----------------------------------------------------


async def embedding_match(
    title: str,
    qdrant_client: AsyncQdrantClient | None,
    gemini: GeminiAdapter | None,
) -> EntityMatch | None:
    """Tầng 3 — so vector tiêu đề bài với vector tên game trong Qdrant.

    Nhận **tiêu đề**, không phải toàn văn bài. Vector của cả bài trôi về phía
    chủ đề chung của bài chứ không về phía cái tên trong đó; mà thứ ta đang tìm
    là một cái tên. Đây cũng đúng thứ `embedding_text` bên `services/embeddings`
    nạp vào, nên hai bên so cùng một loại nội dung.

    Thiếu Qdrant hoặc thiếu key Gemini thì trả None, **không** ném lỗi: tầng 3
    hỏng chỉ nên làm giảm tỉ lệ tự động, còn bài thì đã có sẵn đường đi tiếp là
    hàng đợi duyệt tay.
    """
    if qdrant_client is None or gemini is None or not gemini.configured:
        return None

    text = title.strip()
    if not text:
        return None

    try:
        vectors = await gemini.embed([text])
    except AdapterError as exc:
        logger.warning("không sinh được vector cho tiêu đề", extra={"error": repr(exc)})
        return None
    if not vectors or not vectors[0]:
        return None

    try:
        hits = await embeddings.search(
            qdrant_client, vectors[0], threshold=EMBEDDING_THRESHOLD, limit=2
        )
    except Exception as exc:
        # Bắt rộng có chủ ý: client Qdrant ném cả lỗi mạng (httpx), lỗi API
        # (`UnexpectedResponse`) lẫn `ValueError` khi collection chưa tồn tại.
        # Không cái nào đáng để làm hỏng một lượt crawl — bài rớt xuống hàng
        # đợi duyệt tay là đúng hành vi cần có.
        logger.warning("không truy vấn được Qdrant", extra={"error": repr(exc)})
        return None

    if not hits:
        return None

    # Hai ứng viên sát điểm nhau nghĩa là vector không phân biệt được chúng —
    # thường là hai phần của cùng một series ("Persona 3" và "Persona 5"). Gắn
    # bừa một trong hai đúng vào kiểu sai mà `PHASE-6.md` bảo phải tránh, nên
    # đẩy sang duyệt tay.
    if len(hits) > 1 and (hits[0][1] - hits[1][1]) < EMBEDDING_MARGIN:
        logger.info(
            "hai entity sát điểm nhau ở tầng embedding, chuyển duyệt tay",
            extra={"title": title[:120], "top": hits[0][1], "second": hits[1][1]},
        )
        return None

    game_id, score = hits[0]
    return EntityMatch(
        game_id=game_id,
        tier="embedding",
        confidence=score,
        matched_on=f"cosine={score:.3f}",
    )


# --- Ghép ba tầng ----------------------------------------------------------


async def match_entity(
    db: Db,
    article_title: str,
    article_content: str,
    qdrant_client: AsyncQdrantClient | None = None,
    gemini: GeminiAdapter | None = None,
) -> EntityMatch:
    """Chạy lần lượt ba tầng, dừng ở tầng đầu tiên đủ tin cậy."""
    if (exact := await match_by_store_link(db, article_content)) is not None:
        logger.info(
            "gắn entity qua link store",
            extra={"game_id": str(exact.game_id), "matched_on": exact.matched_on},
        )
        return exact

    if (alias := await match_by_alias(db, article_title)) is not None:
        logger.info(
            "gắn entity qua alias",
            extra={"game_id": str(alias.game_id), "matched_on": alias.matched_on},
        )
        return alias

    if (embed := await embedding_match(article_title, qdrant_client, gemini)) is not None:
        logger.info(
            "gắn entity qua embedding",
            extra={"game_id": str(embed.game_id), "matched_on": embed.matched_on},
        )
        return embed

    logger.info("không gắn được entity, chuyển duyệt tay", extra={"title": article_title[:120]})
    return NO_MATCH
