FROM python:3.12-slim AS base

# uv: cài phụ thuộc nhanh và tái lập được từ lock file
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /srv

# Font có đủ dấu tiếng Việt cho ảnh thẻ chia sẻ (`app/api/seo.py`). Image slim
# không có font nào; font mặc định của Pillow là bitmap không có "ă", "ặ", "₫" —
# thẻ Facebook/Zalo ra toàn ô vuông. Kho Debian chính thức, miễn phí.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Lớp phụ thuộc tách riêng khỏi lớp source để đổi code không phải cài lại
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app

# Không chạy bằng root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# Mặc định là API. Service `worker` ghi đè command trong docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
