# PHASE 6 — Tin tức & dịch

## Trước khi bắt đầu

Đọc `CLAUDE.md`, `PLAN.md`, `DATA-SOURCES.md`, `SCHEMA.md`, `PROGRESS.md`.
Xác nhận Phase 5 đã đạt checkpoint.

## Ranh giới bản quyền — đọc trước khi làm bất cứ gì

- **Không tái bản nguyên văn** bài viết của bên khác
- Lưu và hiển thị: tiêu đề + link gốc + ghi nguồn + **tóm tắt tự viết, tối đa
  3 câu**
- Không dựng lại cấu trúc bài gốc, không tóm tắt chi tiết tới mức thay thế
  việc đọc bản gốc
- Không lấy điểm tổng hợp của Metacritic

Nếu một yêu cầu nào đó đẩy ra ngoài ranh giới này, dừng và hỏi.

## Mục tiêu

Feed tin tức tiếng Việt, gắn đúng vào entity game, cập nhật trong vòng 2 giờ.

Giá trị lõi ở đây **không phải** là tổng hợp tin, mà là đưa tin thế giới sang
tiếng Việt trong ngày — thứ mà lượng nội dung game tiếng Việt hiện có không
đáp ứng được.

## Việc cần làm, theo thứ tự

### 1. Quản lý nguồn

Collection `sources`: tên, URL feed, ngôn ngữ, độ tin cậy, trạng thái, lần
crawl cuối. Admin bật/tắt và thêm nguồn.

Ưu tiên tuyệt đối RSS/API. HTML crawler chỉ là phương án cuối, và mỗi crawler
HTML phải có test riêng để phát hiện khi trang đổi cấu trúc.

Bắt đầu với 10–15 nguồn, cả tiếng Việt và tiếng Anh.

### 2. Khử trùng lặp

Simhash trên nội dung. Một tin lớn sẽ về từ 20 nguồn cùng lúc — nếu không khử
thì feed thành rác ngay ngày đầu.

Bài trùng trỏ `duplicate_of` về bài gốc, giữ lại để đếm "bao nhiêu nguồn đưa
tin này" (tín hiệu hữu ích cho chỉ số hot ở Phase 7).

### 3. Gắn entity — ba tầng

Đây là phần khó nhất và là nơi hệ thống dễ hỏng nhất.

1. **Exact** — tìm link store (Steam/Epic) trong nội dung bài, tra
   `find_game_by_external_id`. Tin cậy cao nhất.
2. **Fuzzy** — khớp tên với `aliases_normalized`. Đặt ngưỡng cẩn thận, thà bỏ
   sót còn hơn gắn sai.
3. **Embedding** — Qdrant, cho trường hợp hai tầng trên không chắc.

Dưới ngưỡng tin cậy → đẩy vào `entity_review_queue`, không đoán bừa.

### 4. Vòng phản hồi — bắt buộc

Mỗi lần duyệt tay trong `entity_review_queue` phải **tự động sinh alias mới**
cho `games.aliases` và `aliases_normalized`.

Không có vòng này thì sẽ phải duyệt tay mãi mãi và hệ thống không bao giờ khá
lên. Đây là yêu cầu bắt buộc, không phải tối ưu.

### 5. LLM adapter — tóm tắt và dịch

Nằm sau `adapters/llm/`, thay thế được. Hỗ trợ ít nhất hai backend: một API
tầng miễn phí (Gemini hoặc Groq, có kiểm soát tốc độ) và một model nhỏ
self-host qua llama.cpp chạy theo hàng đợi nền.

**Chỉ dịch tiêu đề và tóm tắt 2–3 câu, không dịch nguyên bài.** Giảm khoảng 20
lần lượng token và hợp thói quen đọc trên mobile hơn.

Prompt phải yêu cầu viết lại bằng lời của mình, không trích nguyên văn.

Hàng đợi phải chịu được việc backend hết quota giữa chừng: chuyển sang backend
dự phòng, không mất bài.

### 6. Phân loại và feed

Phân loại news / review / preview / guide / deal. Feed cá nhân hoá theo game
đang follow và ngôn ngữ ưu tiên.

## DỪNG LẠI ĐỂ REVIEW

Sau mục 3 (ngưỡng tin cậy của từng tầng — trình bày số liệu thử nghiệm trên
100 bài mẫu trước khi chốt) và sau mục 5 (prompt dịch/tóm tắt).

## Checkpoint nghiệm thu

- [ ] Tỉ lệ gắn entity tự động ≥ 85% trên 200 bài mẫu
- [ ] Tỉ lệ gắn **sai** < 2% (quan trọng hơn tỉ lệ gắn được)
- [ ] Tin quốc tế lên feed tiếng Việt trong vòng 2 giờ
- [ ] Không bài nào hiển thị quá 3 câu, không câu nào trùng nguyên văn nguồn
- [ ] Một tin lớn từ 10 nguồn → feed chỉ hiện 1 bài
- [ ] Duyệt tay 1 bài → alias mới xuất hiện trong entity, bài tương tự sau đó
      gắn được tự động
- [ ] Backend LLM chính hết quota → tự chuyển dự phòng, không mất bài

## Sau khi xong

Cập nhật `PROGRESS.md`. Ghi lại tỉ lệ gắn entity và số bài phải duyệt tay mỗi
ngày — nếu quá 50 bài/ngày thì ngưỡng ở mục 3 cần chỉnh.
