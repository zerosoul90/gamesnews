# PHASE 0 — Nền móng

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Không viết dòng code nào trước khi đọc xong cả năm file.

## Mục tiêu

Dựng khung dự án chạy được bằng một lệnh, chưa có nghiệp vụ nào.

## Phạm vi

**LÀM:** cấu trúc thư mục, docker-compose, skeleton FastAPI, config, logging,
health check, interface adapter, CI.

**KHÔNG LÀM:** gọi bất kỳ API bên ngoài nào, đồng bộ dữ liệu, model nghiệp vụ,
giao diện. Những thứ đó thuộc phase sau.

## Việc cần làm, theo thứ tự

### 1. Cấu trúc và phụ thuộc

Tạo cây thư mục đúng như phần "Cấu trúc" trong `CLAUDE.md`.
`pyproject.toml` với: fastapi, uvicorn, pydantic v2, pydantic-settings, motor,
redis, httpx, ruff, mypy, pytest, pytest-asyncio.

### 2. docker-compose.yml

Năm service: `app`, `mongo`, `meilisearch`, `qdrant`, `redis`.
Volume có tên cho dữ liệu bền. Biến môi trường qua `.env`, kèm `.env.example`
không chứa secret thật. Không expose cổng DB ra ngoài trừ khi cần debug.

### 3. Core

- `core/config.py` — pydantic-settings, đọc toàn bộ từ env, không hardcode
- `core/logging.py` — log dạng JSON, có request id
- `core/db.py` — client Motor, khởi tạo/đóng theo lifespan của FastAPI
- `core/deps.py` — dependency dùng chung

### 4. Health check

`GET /health` kiểm tra thật cả bốn phụ thuộc (ping Mongo, Meilisearch, Qdrant,
Redis), trả về trạng thái từng cái và HTTP 503 nếu có cái nào hỏng.

### 5. adapters/base.py

Định nghĩa interface chung cho mọi nguồn ngoài. Tối thiểu phải có:

- phương thức async chuẩn hoá về model nội bộ
- rate limiter dạng token bucket, cấu hình được, **chia sẻ được giữa nhiều job**
  (Steam giới hạn theo IP nên mọi job gọi Steam phải dùng chung một bucket)
- retry với exponential backoff
- phân biệt lỗi tạm thời và lỗi vĩnh viễn
- hook ghi log mỗi lần gọi để về sau đo được mức tiêu thụ quota

Viết kèm một adapter giả (`adapters/dummy/`) để chứng minh interface dùng được,
và test cho rate limiter.

### 6. CI

GitHub Actions: ruff check, mypy, pytest. Phải xanh.

### 7. Đăng ký key ngoài

Ghi vào `.env.example` các biến cần: `STEAM_API_KEY`, `TWITCH_CLIENT_ID`,
`TWITCH_CLIENT_SECRET`. Báo lại cho tôi biết cần tự đăng ký ở đâu.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 2 (docker-compose) và sau mục 5 (adapters/base.py). Trình bày thiết kế
trước, chờ tôi duyệt rồi mới viết tiếp.

## Checkpoint nghiệm thu

- [ ] `docker compose up` khởi động toàn bộ stack không lỗi
- [ ] `GET /health` trả 200 với trạng thái xanh của cả 4 phụ thuộc
- [ ] Tắt riêng Meilisearch → `/health` trả 503 và chỉ đúng service hỏng
- [ ] `ruff`, `mypy`, `pytest` đều sạch
- [ ] Không có secret nào bị commit

## Sau khi xong

Cập nhật `PROGRESS.md`: tick các mục Phase 0, ghi nhật ký, ghi lại mọi quyết
định phát sinh khác với tài liệu.
