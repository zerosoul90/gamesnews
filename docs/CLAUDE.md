# CLAUDE.md — Quy ước dự án

Đọc file này đầu mỗi phiên. Đọc kèm `PROGRESS.md` để biết đang ở đâu.

## Bối cảnh

Nền tảng tổng hợp thông tin game đa ngôn ngữ, ưu tiên thị trường Việt Nam.
Web + Android + iOS. Chi tiết ở `PLAN.md`.

Ba tài liệu tham chiếu, luôn đọc trước khi viết code:

- `PLAN.md` — lộ trình, phase hiện tại, checkpoint
- `DATA-SOURCES.md` — nguồn nào được dùng, nguồn nào **cấm**, giới hạn cụ thể
- `SCHEMA.md` — mô hình dữ liệu

## Luật vàng

1. **Làm theo phase, dừng ở checkpoint.** Không nhảy sang phase sau khi
   checkpoint hiện tại chưa đạt. Không tự mở rộng phạm vi.
2. **Dừng lại để review** ở cuối mỗi hạng mục lớn. Đề xuất trước, chờ duyệt,
   rồi mới viết.
3. **Mọi nguồn dữ liệu nằm sau một adapter.** Không gọi thẳng API bên thứ ba
   từ business logic. Tầng miễn phí có thể biến mất bất cứ lúc nào.
4. **Không dùng nguồn nằm trong danh sách cấm** của `DATA-SOURCES.md`
   (ITAD, SteamDB, OpenCritic, Epic library API, dịch vụ scraping trả phí).
   Nếu thấy một nguồn tiện hơn nhưng chưa có trong tài liệu — hỏi trước, không
   tự thêm.
5. **Không phát sinh chi phí.** Nếu một giải pháp cần dịch vụ trả tiền, dừng
   lại và báo, đừng tự chọn.
6. **Cập nhật `PROGRESS.md`** sau mỗi hạng mục hoàn thành.

## Quy ước kỹ thuật

- Python 3.12, FastAPI, async xuyên suốt
- Pydantic v2 cho mọi input/output biên
- Motor cho MongoDB; không dùng driver đồng bộ
- Cấu hình qua biến môi trường, `pydantic-settings`, không hardcode
- Secret (Steam Web API key, Twitch client secret, FCM key) **chỉ ở server**,
  không bao giờ lộ ra client
- Type hint đầy đủ; ruff + mypy phải sạch trước khi commit
- Nội dung tĩnh dạng JSON, không nhúng vào code
- Job nền chạy bằng Arq (worker riêng, Redis làm broker), không tự viết vòng
  lặp scheduler trong tiến trình API
- Web: Angular + TypeScript, luôn bật `@angular/ssr`
- Mobile: Flutter + Dart, state bằng Riverpod
- Ngôn ngữ nội dung MVP: Việt + Anh

## Cấu trúc

```
app/
  api/            # router FastAPI
  core/           # config, logging, deps
  models/         # pydantic + document schema
  adapters/       # MỘT thư mục con cho mỗi nguồn ngoài
    steam/
    epic/
    igdb/
    twitch/
    llm/          # adapter dịch/tóm tắt, thay được
  services/       # business logic, không biết nguồn nào đứng sau
  jobs/           # scheduler, crawler, rollup
  search/         # meilisearch + qdrant
tests/
```

Mỗi adapter cài đặt một interface chung trong `adapters/base.py`. Service không
được import trực tiếp một adapter cụ thể.

## Ranh giới không được vượt

- **Không tái bản nguyên văn** nội dung có bản quyền. Bài viết chỉ lưu tiêu đề
  + link + tóm tắt tự viết (tối đa 3 câu).
- **Không lấy điểm tổng hợp của Metacritic.** Điểm phê bình tự tính bằng công
  thức trọng số riêng.
- **Không lưu dữ liệu người dùng quá mức cần.** Thư viện Steam chỉ lưu appid +
  playtime + mốc đồng bộ. Không lịch sử mua.
- **Không bao giờ** gửi cảnh báo giảm giá cho game người dùng đã sở hữu.

## Rate limit phải tôn trọng

| Nguồn | Giới hạn | Cách xử lý |
|---|---|---|
| Steam appdetails | ~200 req/5 phút mỗi IP, 1 appid + 1 region mỗi request | scheduler phân tầng hot/ấm/lạnh; token bucket dùng chung |
| IGDB | ~4 req/s | |
| YouTube Data API | 10.000 units/ngày, search tốn 100 | chỉ nhóm hot; live dùng WebSub |
| Liquipedia | giãn request, User-Agent riêng, ghi nguồn | |

Mọi adapter phải có backoff và không được để một job làm cạn quota của job khác.

## Khi bí

Nếu một yêu cầu mâu thuẫn với tài liệu, hoặc cần một nguồn/dịch vụ chưa có
trong `DATA-SOURCES.md` — **dừng và hỏi**, đừng tự quyết.
