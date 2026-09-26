"""Gắn bài viết vào entity game — `docs/PHASE-6.md` mục 3.

Tài liệu gọi đây là "phần khó nhất và là nơi hệ thống dễ hỏng nhất", và đặt ra
một nguyên tắc chi phối mọi ngưỡng trong file này:

> **thà bỏ sót còn hơn gắn sai.**

Lý do: bài bị bỏ sót thì nằm trong hàng đợi duyệt tay, ai cũng thấy và sửa
được trong mười giây. Bài bị gắn nhầm thì hiển thị lặng lẽ dưới trang một game
khác, không ai báo, và còn kéo theo chỉ số hot của Phase 7 sai theo.

Bốn tầng, tin cậy giảm dần:

1. **Exact** — có link store trong bài, tra ngược ra entity. Chắc chắn nhất.
2. **Alias** — một cụm từ trong tiêu đề trùng khít một alias đã chuẩn hoá.
3. **LLM alias** — LLM đọc bài và nói tên game, rồi tên đó đi qua đúng bộ máy
   alias của tầng 2.
4. **Embedding** — vector **tên game** trong Qdrant (`services/embeddings.py`).

Không tầng nào đủ tin cậy thì trả `manual`, và người gọi có nghĩa vụ đẩy bài
vào `entity_review_queue` (xem `services/entity_review.py`). Không đoán bừa.

**Vì sao tầng 3 và 4 nhận TÊN chứ không nhận tiêu đề.** Bản trước đem cả câu
tiêu đề đi so với vector của một cái tên. Đo thật 2026-09-13 trên 20 bài trong
hàng đợi duyệt tay, so với 450 vector:

| điểm | entity gần nhất | tiêu đề |
|---|---|---|
| 0.671 | Sniper Elite V2 | "Aliens: Fireteam Elite 2 Review" |
| 0.620 | Warhammer 40,000: Space Marine | "How Warhammer 40,000: Space Marine 3 Will Benefit…" |
| 0.515 | Monsters! | "The 9 Biggest Trailers Worth Watching This Week" |

Toàn bộ nằm trong 0.49 tới 0.67, và **điểm cao nhất cả mẫu lại là một cặp SAI** —
khớp nhau chỉ vì chữ "Elite". Cặp đúng duy nhất còn xếp dưới nó. Nghĩa là hạ
ngưỡng để tầng cuối "chạy được" sẽ rước cái sai vào trước cái đúng, ngược hẳn
nguyên tắc đầu file.

Đó chính là sai lầm `PROGRESS.md` đã ghi cho tầng 2 hôm 2026-09-09 — *"so CẢ
tiêu đề với alias bằng SequenceMatcher nên tiêu đề tin thật luôn ra ~0.4"* —
lặp lại dưới dạng vector. Không ngưỡng nào chữa được chuyện so sai thứ.

Thuốc vốn đã nằm trong nhà: prompt ở `adapters/llm/gemini.py` từ đầu đã bảo LLM
trả `suggested_alias` ("tên gốc của game được nhắc tới nhiều nhất"), model vẫn
điền nó ở mỗi bài, và **không chỗ nào đọc tới**. Nay nó là đầu vào của tầng 3
và 4 — so tên với tên, không tốn thêm một lời gọi nào.
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

MatchTier = Literal["exact", "alias", "llm_alias", "embedding", "manual"]

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

# Cùng phép khớp khít như trên, nhưng chuỗi đem đi khớp do LLM đọc bài rồi
# **viết ra**, chứ không trích từ bài. Model có thể viết sai tên, hoặc viết tên
# một game chỉ được nhắc thoáng qua. Phép khớp thì chắc; nguồn của chuỗi thì
# không — nên thấp hơn một bậc, và người duyệt tay nhìn số này biết ngay là
# entity đến từ đâu.
LLM_ALIAS_CONFIDENCE = 0.85

# Ngưỡng cosine của tầng 4. Hiệu chỉnh 2026-09-26 (lượt 28 ở `PROGRESS.md`):
#
# - Trên dữ liệu thật, mọi bài gắn ở tầng này với điểm dưới 0.99 đều **sai** (3/3,
#   ở 0.837-0.841 — ngay trên ngưỡng cũ 0.82): hai bài "Tropico 7" vào Tropico 5,
#   một bài RPG chung chung vào Divinity II.
# - 42 tên đo tay có đáp án: cặp đúng trải 0.72-0.97, cặp sai 0.64-0.84. Hai phân
#   bố **chồng lên nhau**, không ngưỡng nào tách sạch. 0.85 là mức thấp nhất bỏ
#   được mọi cặp sai đã thấy; cái giá là 5/11 cặp đúng qua được 0.82 rơi xuống duyệt
#   tay — đúng chiều nguyên tắc đầu file.
# - Hai phần khác nhau của một series giống nhau tới 0.97 (so từng cặp vector
#   trong Qdrant, 2.158 game). Ngưỡng không chặn được kiểu sai đó; phép kiểm số
#   phần trong `embedding_match` mới chặn được.
EMBEDDING_THRESHOLD = 0.85

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


# Số La Mã đánh số phần, dạng đã qua `normalize_vi` (thường hoá). Không có "i":
# nó trùng đại từ tiếng Anh, còn "Phần I" thì hiếm khi được viết ra.
_ROMAN = {
    "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17,
    "xviii": 18, "xix": 19, "xx": 20,
}


def sequel_number(token: str) -> int | None:
    """Số thứ tự phần mà một từ (đã chuẩn hoá) biểu diễn, hoặc None.

    Chỉ số một hai chữ số: "2077", "1997" là tên hoặc năm, không phải số phần.
    """
    if token.isdigit() and len(token) <= 2:
        return int(token)
    return _ROMAN.get(token)


def sequel_numbers(normalized: str) -> set[int]:
    return {n for word in normalized.split() if (n := sequel_number(word)) is not None}


def followed_by_sequel(words: list[str], end: int) -> bool:
    """Từ `words[end]` — ngay sau một cụm — có phải số phần không.

    Trừ số phiên bản: `normalize_vi` biến "2.0" thành "2 0", nên một con số mà
    ngay sau nó là một con số nữa ("cyberpunk 2077 2 0 update") thì không phải
    số phần.
    """
    if end >= len(words) or sequel_number(words[end]) is None:
        return False
    after = words[end + 1] if end + 1 < len(words) else ""
    return not (words[end].isdigit() and after.isdigit())


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


def grams_before_sequel(normalized: str, max_words: int = MAX_ALIAS_WORDS) -> set[str]:
    """Những cụm đứng ngay trước một số phần — "far cry" trong "far cry 6"."""
    words = normalized.split()
    return {
        " ".join(words[start:end])
        for end in range(1, len(words))
        if followed_by_sequel(words, end)
        for start in range(max(0, end - max_words), end)
    }


def is_specific_enough(alias: str) -> bool:
    """Alias có đủ đặc trưng để tin hay không.

    Một từ ngắn thì gần như chắc chắn là từ thông thường lọt vào danh sách
    alias, không phải tên game.
    """
    return len(alias.split()) >= 2 or len(alias) >= MIN_SINGLE_WORD_CHARS


async def match_by_alias(
    db: Db,
    title: str,
    *,
    tier: MatchTier = "alias",
    confidence: float = ALIAS_CONFIDENCE,
) -> EntityMatch | None:
    """Tầng 2: một cụm trong tiêu đề trùng khít một alias đã chuẩn hoá.

    `tier` và `confidence` tham số hoá được vì tầng 3 dùng **đúng phép khớp
    này**, chỉ khác chuỗi đầu vào là tên do LLM viết ra chứ không phải tiêu đề.
    Viết lại một bản thứ hai cho tầng 3 thì hai bản sẽ trôi khỏi nhau, mà luật
    "hai game cùng khớp thì không chọn cái nào" là thứ không được phép chỉ đúng
    ở một trong hai đường.

    Trùng khít chứ không phải "gần giống": `normalize_vi` đã lo phần bỏ dấu,
    thường hoá và bỏ ký tự đặc biệt — tức phần lớn khác biệt thật giữa cách
    viết. Thêm một tầng đo độ giống chuỗi lên trên đó chỉ mở đường cho gắn sai,
    mà chỗ để sửa những ca đó là vòng phản hồi alias ở `entity_review.py`.

    Hai game cùng khớp một cụm dài như nhau thì **không chọn cái nào**: đó
    đúng là lúc con người cần nhìn vào.

    **Cụm đứng trước số phần không được gắn** ("far cry" trong "Far Cry 6"), và
    nếu nó dài bằng hoặc hơn mọi cụm khớp khác thì cả tiêu đề chuyển duyệt tay.
    Catalog có "Far Cry 6" thì cụm dài hơn đã thắng; tới được đây nghĩa là phần
    đó **chưa có**, và bài đang nói về nó. Đo 2026-09-26 trên 2.145 bài thật: 49
    bài đổi kết quả. Mọi ca bị bỏ là gắn sai — Mortal Shell 2, Endless Legend 2,
    Black Ops 7, "Final Fantasy 7 Revelation" vào `final-fantasy`. Còn chỉ bỏ
    cụm đó rồi xét tiếp thì alias rác ngắn hơn nó vẫn che lâu nay nổi lên thắng:
    "Final Fantasy 7 **Revelation**" ra một game Android tên Revelation, cùng
    "the last", "the master", "in sight".
    """
    normalized = normalize_vi(title)
    if not normalized:
        return None

    candidates = [gram for gram in ngrams(normalized) if is_specific_enough(gram)]
    if not candidates:
        return None
    before_sequel = grams_before_sequel(normalized)

    # Một truy vấn duy nhất cho mọi cụm; `aliases_normalized` là index multikey
    # nên đây là index scan, không phải quét bảng.
    cursor = games(db).find(
        {"aliases_normalized": {"$in": candidates}},
        {"aliases_normalized": 1, "slug": 1},
    )

    best_len = 0
    best: list[tuple[ObjectId, str]] = []
    sequel_len = 0
    async for doc in cursor:
        aliases = set(doc.get("aliases_normalized") or [])
        for gram in candidates:
            if gram not in aliases:
                continue
            length = len(gram.split())
            if gram in before_sequel:
                sequel_len = max(sequel_len, length)
                continue
            if length > best_len:
                best_len, best = length, [(doc["_id"], gram)]
            elif length == best_len and doc["_id"] not in [x for x, _ in best]:
                best.append((doc["_id"], gram))
            break

    if sequel_len and sequel_len >= best_len:
        logger.info(
            "tiêu đề nói về một phần chưa có trong catalog, chuyển duyệt tay",
            extra={"title": title[:120]},
        )
        return None

    if not best:
        return None

    if len(best) > 1:
        logger.info(
            "nhiều game cùng khớp một cụm, chuyển duyệt tay",
            extra={"title": title[:120], "matches": len(best)},
        )
        return None

    game_id, alias = best[0]
    return EntityMatch(game_id=game_id, tier=tier, confidence=confidence, matched_on=alias)


# --- Tầng 3: embedding -----------------------------------------------------


async def embedding_match(
    game_name: str,
    qdrant_client: AsyncQdrantClient | None,
    gemini: GeminiAdapter | None,
) -> EntityMatch | None:
    """Tầng 4 — so vector một TÊN GAME với vector tên game trong Qdrant.

    `game_name` là tên do LLM trích ra, **không phải tiêu đề bài**. Bản trước
    nhận tiêu đề, và phép đo ở đầu file cho thấy đó là so sai thứ: cả câu tiêu
    đề đem so với một cái tên thì điểm dồn hết vào 0.49 tới 0.67, và cặp điểm cao
    nhất lại là cặp sai. `embedding_text` bên `services/embeddings` nạp vào
    Qdrant đúng **tên và alias**, nên đầu kia cũng phải là một cái tên thì hai
    bên mới so cùng một loại nội dung.

    Thiếu Qdrant hoặc thiếu key Gemini thì trả None, **không** ném lỗi: tầng
    này hỏng chỉ nên làm giảm tỉ lệ tự động, còn bài thì đã có sẵn đường đi tiếp
    là hàng đợi duyệt tay.
    """
    if qdrant_client is None or gemini is None or not gemini.configured:
        return None

    text = game_name.strip()
    if not text:
        return None

    try:
        vectors = await gemini.embed([text])
    except AdapterError as exc:
        logger.warning("không sinh được vector cho tên game", extra={"error": repr(exc)})
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
            extra={"game_name": text[:120], "top": hits[0][1], "second": hits[1][1]},
        )
        return None

    # Số phần trong tên LLM trích ra phải có mặt trong tên entity. "Tropico 7"
    # ra Tropico 5 ở 0.841, "Street Fighter 6" ra Street Fighter V ở 0.80: vector
    # gần vì gần như cùng chữ, còn con số — thứ duy nhất phân biệt hai game — thì
    # vector gần như không thấy. Chiều ngược lại thì không đòi: "Skyrim" phải ra
    # được "The Elder Scrolls V: Skyrim".
    game_id, score, entity_name = hits[0]
    missing = sequel_numbers(normalize_vi(text)) - sequel_numbers(normalize_vi(entity_name))
    if missing:
        logger.info(
            "số phần không khớp ở tầng embedding, chuyển duyệt tay",
            extra={"game_name": text[:120], "entity": entity_name[:120], "score": score},
        )
        return None

    return EntityMatch(
        game_id=game_id,
        tier="embedding",
        confidence=score,
        matched_on=f"cosine={score:.3f}",
    )


# --- Ghép bốn tầng ---------------------------------------------------------


async def match_entity(
    db: Db,
    article_title: str,
    article_content: str,
    qdrant_client: AsyncQdrantClient | None = None,
    gemini: GeminiAdapter | None = None,
    *,
    suggested_alias: str | None = None,
) -> EntityMatch:
    """Chạy lần lượt bốn tầng, dừng ở tầng đầu tiên đủ tin cậy.

    `suggested_alias` là tên game do LLM đọc bài rồi trích ra. Thiếu nó thì hai
    tầng cuối **không chạy** và bài rơi thẳng xuống duyệt tay — đó là hành vi
    đúng, không phải thiếu sót: không có tên thì không có gì để so, mà đem tiêu
    đề ra so thay thì đã đo là sai (xem đầu file).
    """
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

    name = (suggested_alias or "").strip()
    if name:
        # Tầng 3 trước tầng 4: cùng một cái tên, nhưng khớp khít trên chuỗi đã
        # chuẩn hoá thì chắc hơn hẳn so vector, và không tốn lời gọi nào.
        llm = await match_by_alias(db, name, tier="llm_alias", confidence=LLM_ALIAS_CONFIDENCE)
        if llm is not None:
            logger.info(
                "gắn entity qua tên LLM trích ra",
                # `game_name`, KHÔNG phải `name`: `name` là thuộc tính dành
                # riêng của `LogRecord` và `logging` ném `KeyError` khi bị ghi
                # đè. Nó chỉ nổ khi logger đang bật ở mức INFO — tức là ở
                # production, còn chạy test lẻ thì `logger.info` thoát sớm nên
                # không ai thấy.
                extra={
                    "game_id": str(llm.game_id),
                    "matched_on": llm.matched_on,
                    "game_name": name,
                },
            )
            return llm

        if (embed := await embedding_match(name, qdrant_client, gemini)) is not None:
            logger.info(
                "gắn entity qua embedding",
                extra={"game_id": str(embed.game_id), "matched_on": embed.matched_on},
            )
            return embed

    logger.info(
        "không gắn được entity, chuyển duyệt tay",
        extra={"title": article_title[:120], "suggested_alias": name or None},
    )
    return NO_MATCH
