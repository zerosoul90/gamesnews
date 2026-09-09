"""Interface chung cho mọi nguồn dữ liệu ngoài.

Service không bao giờ import một adapter cụ thể — chỉ làm việc qua lớp này.
Tầng miễn phí của bên thứ ba có thể biến mất bất cứ lúc nào, thay adapter phải
không đụng tới business logic.

Bốn thứ mọi adapter đều được thừa hưởng:

- token bucket **nằm trong Redis**, nên nhiều job ở nhiều tiến trình dùng chung
  một hạn mức (Steam giới hạn theo IP, không theo tiến trình)
- retry với exponential backoff + jitter, chỉ retry lỗi tạm thời
- phân biệt lỗi tạm thời và lỗi vĩnh viễn
- hook ghi log mỗi lần gọi, để về sau đo được mức tiêu thụ quota
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- lỗi


class AdapterError(Exception):
    """Gốc của mọi lỗi phát ra từ tầng adapter."""


class TransientError(AdapterError):
    """Lỗi có thể tự khỏi: timeout, 5xx, đứt mạng. Được phép retry."""


class PermanentError(AdapterError):
    """Lỗi retry vô nghĩa: 400, 401, 404, dữ liệu sai định dạng."""


class RateLimitedError(TransientError):
    """Hết token trong bucket, hoặc bên kia trả 429."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def classify_http_status(status_code: int) -> type[AdapterError] | None:
    """Quy mã HTTP về loại lỗi. None nghĩa là không phải lỗi."""
    if status_code < 400:
        return None
    if status_code == 429:
        return RateLimitedError
    if status_code >= 500:
        return TransientError
    if status_code in (408, 425):
        return TransientError
    return PermanentError


# ----------------------------------------------------------- rate limit

# Token bucket chạy nguyên tử trong Redis. Đọc - tính - ghi phải nằm trong một
# script, nếu tách ra thì hai worker cùng đọc một trạng thái và cùng tưởng
# mình còn token.
_BUCKET_LUA = """
local capacity  = tonumber(ARGV[1])
local rate      = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now_ms    = tonumber(ARGV[4])

-- now_ms < 0: lay dong ho cua Redis. Worker va API co the o hai may khac
-- nhau, dung dong ho chung moi tranh lech gio. Test truyen now_ms de tu
-- dieu khien thoi gian.
if now_ms < 0 then
  local t = redis.call('TIME')
  now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end

local state  = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts     = tonumber(state[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now_ms
end

local elapsed = now_ms - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + (elapsed / 1000.0) * rate)

local allowed = 0
local wait_ms = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  wait_ms = math.ceil(((requested - tokens) / rate) * 1000)
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now_ms)
-- Giu key du lau de bucket day lai; quen som hon la tu cho them quota.
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity / rate) * 1000) + 60000)

return {allowed, wait_ms}
"""


class RateLimiter(Protocol):
    """Cái mà adapter cần ở một rate limiter. `RedisTokenBucket` là bản cài
    dùng trong sản phẩm; test dùng bản giả để khỏi cần Redis."""

    async def acquire(self, tokens: int = 1) -> None: ...


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Hạn mức của một nguồn. Ví dụ Steam appdetails: 200 request / 300 giây."""

    capacity: int
    per_seconds: float

    @property
    def refill_per_second(self) -> float:
        return self.capacity / self.per_seconds


class RedisTokenBucket:
    """Token bucket dùng chung giữa mọi tiến trình nói cùng một Redis.

    Một bucket cho mỗi `key`. Mọi job gọi Steam phải dùng chung một key, nếu
    không thì mỗi job có hạn mức riêng và tổng số request vượt quota của IP.
    """

    def __init__(
        self,
        redis: Redis,
        key: str,
        limit: RateLimit,
        *,
        max_wait_seconds: float = 30.0,
    ) -> None:
        self._redis = redis
        self._key = f"ratelimit:{key}"
        self._limit = limit
        self._max_wait_seconds = max_wait_seconds
        self._script = redis.register_script(_BUCKET_LUA)

    @property
    def key(self) -> str:
        return self._key

    async def try_acquire(self, tokens: int = 1, *, now_ms: int | None = None) -> float:
        """Lấy token. Trả về 0.0 nếu được, hoặc số giây phải chờ nếu chưa được.

        `now_ms` chỉ dùng cho test; mặc định lấy đồng hồ của Redis.
        """
        if tokens > self._limit.capacity:
            raise PermanentError(
                f"xin {tokens} token nhưng bucket chỉ chứa tối đa {self._limit.capacity}"
            )
        raw = await self._script(
            keys=[self._key],
            args=[
                self._limit.capacity,
                self._limit.refill_per_second,
                tokens,
                -1 if now_ms is None else now_ms,
            ],
        )
        # Script trả về {allowed, wait_ms}; redis-py không biết kiểu nên ép tay.
        allowed, wait_ms = (int(value) for value in tuple(raw)[:2])
        return 0.0 if allowed else wait_ms / 1000.0

    async def acquire(self, tokens: int = 1) -> None:
        """Chờ tới khi lấy được token. Quá `max_wait_seconds` thì báo lỗi thay
        vì treo job — để scheduler còn biết mà giãn tầng."""
        waited = 0.0
        while True:
            wait = await self.try_acquire(tokens)
            if wait == 0.0:
                return
            if waited + wait > self._max_wait_seconds:
                raise RateLimitedError(
                    f"bucket {self._key} cạn, cần chờ thêm {wait:.1f}s "
                    f"(trần {self._max_wait_seconds:.1f}s)",
                    retry_after_seconds=wait,
                )
            await asyncio.sleep(wait)
            waited += wait


class SlidingWindowRateLimiter:
    """Cửa sổ trượt, **nằm trong bộ nhớ tiến trình**. Bảo đảm yếu hơn hẳn
    `RedisTokenBucket` — đọc kỹ đoạn này trước khi dùng.

    Mỗi tiến trình có cửa sổ riêng. Chạy hai worker là tổng số request gấp đôi
    con số `limit` ghi ở đây. Vì vậy nó **không dùng được** cho hạn mức tính
    theo IP như `appdetails` của Steam (~200 req/5 phút) — chỗ đó bắt buộc
    `RedisTokenBucket`, nếu không mỗi worker lại tưởng mình còn nguyên quota.

    Chỉ dùng khi cả ba điều sau đều đúng:

    1. hạn mức tính theo key hoặc theo tài khoản, không theo IP;
    2. trần rộng so với lưu lượng thật (Steam Web API: 100.000 lượt/ngày mỗi
       key), nên vượt một chút không bị chặn;
    3. lời gọi do người dùng bấm mà sinh ra, không phải job nền quét hàng loạt.

    `GetOwnedGames` ở `services/user_library.py` thoả cả ba: nó chỉ chặn một
    người bấm đồng bộ liên tục, chứ không phải công cụ chia quota giữa các job.
    """

    def __init__(self, limit: int, window_size: float) -> None:
        if limit < 1:
            raise ValueError("limit phải >= 1")
        if window_size <= 0:
            raise ValueError("window_size phải > 0")
        self._limit = limit
        self._window = window_size
        self._hits: deque[float] = deque()
        # Không có lock thì hai coroutine cùng thấy cửa sổ còn chỗ và cùng đi
        # tiếp — đúng lỗi mà chính script Lua ở trên sinh ra để tránh.
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        if tokens > self._limit:
            raise PermanentError(
                f"xin {tokens} lượt nhưng cửa sổ chỉ chứa tối đa {self._limit}"
            )
        async with self._lock:
            while True:
                now = time.monotonic()
                # Đồng hồ monotonic, không phải wall clock: đổi giờ hệ thống
                # không được phép mở toang cửa sổ.
                while self._hits and now - self._hits[0] >= self._window:
                    self._hits.popleft()

                if len(self._hits) + tokens <= self._limit:
                    self._hits.extend([now] * tokens)
                    return

                await asyncio.sleep(self._window - (now - self._hits[0]))


# --------------------------------------------------------------- retry


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    # Jitter để nhiều worker cùng bị 5xx không đồng loạt gọi lại một lúc.
    jitter: float = 0.25

    def delay_for(self, attempt: int) -> float:
        """attempt tính từ 1. Trả về số giây chờ trước lần thử kế tiếp."""
        raw = min(self.base_delay_seconds * 2.0 ** (attempt - 1), self.max_delay_seconds)
        spread = raw * self.jitter
        return max(0.0, raw + random.uniform(-spread, spread))  # noqa: S311


# ------------------------------------------------------- hook ghi nhận


@dataclass(slots=True)
class CallRecord:
    """Một lần gọi ra ngoài. Gom lại để về sau đo mức tiêu thụ quota."""

    source: str
    endpoint: str
    attempt: int
    ok: bool
    duration_ms: float
    cost: int
    error_type: str | None = None
    error: str | None = None


CallHook = Callable[[CallRecord], None]


# ------------------------------------------------------------- adapter

@dataclass(slots=True)
class AdapterConfig:
    limiter: RateLimiter
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    hooks: list[CallHook] = field(default_factory=list)


class BaseAdapter[RawT, ModelT](ABC):
    """Lớp cơ sở cho mọi nguồn ngoài.

    Lớp con chỉ cần cài `fetch_raw` (gọi mạng) và `normalize` (đổi sang model
    nội bộ). Rate limit, retry, phân loại lỗi và ghi log do lớp này lo.
    """

    source: ClassVar[str] = ""

    def __init__(self, config: AdapterConfig) -> None:
        if not type(self).source:
            raise TypeError(f"{type(self).__name__} phải khai báo ClassVar `source`")
        self._config = config

    @property
    def limiter(self) -> RateLimiter:
        return self._config.limiter

    @abstractmethod
    async def fetch_raw(self, **params: Any) -> RawT:
        """Gọi thẳng ra nguồn. Ném TransientError / PermanentError cho đúng loại."""

    @abstractmethod
    def normalize(self, raw: RawT) -> ModelT:
        """Đổi payload thô sang model nội bộ. Không được gọi mạng ở đây."""

    async def fetch(self, *, endpoint: str = "", cost: int = 1, **params: Any) -> ModelT:
        """Đường vào duy nhất mà service được dùng."""
        policy = self._config.retry
        last_error: AdapterError | None = None

        for attempt in range(1, policy.max_attempts + 1):
            # Mỗi lần thử là một request thật, nên lần retry cũng phải trả
            # token. Không tính thì bucket không phản ánh đúng quota đã tiêu.
            await self._config.limiter.acquire(cost)

            started = time.perf_counter()
            try:
                raw = await self.fetch_raw(**params)
            except PermanentError as exc:
                self._record(endpoint, attempt, started, cost, exc)
                raise
            except TransientError as exc:
                self._record(endpoint, attempt, started, cost, exc)
                last_error = exc
            except Exception as exc:
                # Lớp con quên bọc lỗi - coi là vĩnh viễn, đừng retry mù.
                wrapped = PermanentError(f"lỗi chưa phân loại từ {self.source}: {exc!r}")
                self._record(endpoint, attempt, started, cost, wrapped)
                raise wrapped from exc
            else:
                self._record(endpoint, attempt, started, cost, None)
                return self.normalize(raw)

            if attempt < policy.max_attempts:
                delay = policy.delay_for(attempt)
                if isinstance(last_error, RateLimitedError) and last_error.retry_after_seconds:
                    delay = max(delay, last_error.retry_after_seconds)
                await asyncio.sleep(delay)

        if last_error is None:  # pragma: no cover - vòng lặp luôn gán trước khi tới đây
            raise AdapterError(f"{self.source}: hết lượt thử mà không ghi nhận lỗi nào")
        raise last_error

    def _record(
        self,
        endpoint: str,
        attempt: int,
        started: float,
        cost: int,
        error: AdapterError | None,
    ) -> None:
        record = CallRecord(
            source=self.source,
            endpoint=endpoint,
            attempt=attempt,
            ok=error is None,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            cost=cost,
            error_type=type(error).__name__ if error else None,
            error=str(error)[:200] if error else None,
        )
        logger.info(
            "gọi nguồn ngoài",
            extra={
                "source": record.source,
                "endpoint": record.endpoint,
                "attempt": record.attempt,
                "ok": record.ok,
                "duration_ms": record.duration_ms,
                "cost": record.cost,
                "error_type": record.error_type,
            },
        )
        for hook in self._config.hooks:
            hook(record)
