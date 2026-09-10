# GameNews - Hướng dẫn cài đặt và dùng thử

Chào mừng bạn đến với dự án GameNews! Hệ thống bao gồm 3 thành phần chính: Backend (FastAPI + Arq Worker), Frontend Web (Angular SSR), và Mobile App (Flutter). Toàn bộ hạ tầng dữ liệu đã được cấu hình sẵn trong Docker.

Dưới đây là các bước thiết lập môi trường để bạn có thể chạy thử hệ thống ở local.

## Yêu cầu chuẩn bị
- **Docker** và **Docker Compose**
- **Node.js** phiên bản 18 trở lên (để chạy Web)
- **Flutter SDK** phiên bản 3.12+ (để chạy App)
- (Tuỳ chọn) `uv` hoặc Python 3.12 nếu bạn muốn phát triển Backend không dùng Docker.

---

## 1. Khởi động Hạ tầng và Backend

Backend quản lý hàng loạt các cơ sở dữ liệu: MongoDB (Chính), Redis (Hàng đợi & Rate Limit), Meilisearch (Tìm kiếm), Qdrant (Vector Embedding), Postgres (Umami Analytics).

**Bước 1: Khởi tạo biến môi trường**
Tại thư mục gốc, copy file cấu hình mẫu và điền các API key nếu có (quan trọng nhất là `GEMINI_API_KEY` và `STEAM_API_KEY` nếu bạn muốn trải nghiệm tính năng quét deal và AI):
```bash
cp .env.example .env
```

**Bước 2: Khởi chạy Docker Compose**
Chỉ với 1 lệnh, toàn bộ hệ thống API, Worker, Database và Umami Analytics sẽ được dựng lên:
```bash
docker-compose up -d --build
```

**Bước 3: Kiểm tra trạng thái**
- **Swagger UI (Tài liệu API):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Umami Analytics Dashboard:** [http://localhost:3000](http://localhost:3000)

> **Lưu ý dữ liệu mẫu:** Hệ thống ban đầu sẽ trống rỗng. Worker (Arq) được thiết lập chạy nền theo lịch cron để từ từ cào dữ liệu từ Steam, App Store, Google Play. Bạn có thể sử dụng Swagger UI trên cổng 8000 để gọi tay các hàm test nếu không muốn đợi.

---

## 2. Khởi động Web Frontend (Angular)

Web App cung cấp giao diện đọc tin và tìm kiếm cho người dùng cuối. 
Hiện tại, tôi đã thiết lập để Web App tự động chạy chung với hạ tầng Docker ở Bước 1. 

Bạn không cần cài Node.js hay chạy lệnh `npm` thủ công nữa. Khi chạy `docker-compose up -d --build`, web sẽ tự động được build và chạy ở cổng **4200**.
Trang web sẽ hiện lên ở địa chỉ `http://localhost:4200` (cổng mặc định của Angular dev server).

---

## 3. Khởi động Mobile App (Flutter)

Ứng dụng di động cung cấp trải nghiệm native, nhận thông báo đẩy (Push Notification) giảm giá và Widget.

1. Bật máy ảo Android/iOS (Emulator/Simulator) hoặc cắm điện thoại thật.
2. Chuyển vào thư mục `mobile`:
```bash
cd mobile
flutter pub get
flutter run
```

---

## Các tài liệu tham khảo thêm
Để nắm bắt luồng hệ thống chi tiết và thiết kế database, vui lòng đọc các tài liệu trong thư mục `docs/`:
- `SCHEMA.md`: Cấu trúc dữ liệu MongoDB.
- `DATA-SOURCES.md`: Phân tích các nguồn API ngoài (Steam, Epic, Twitch...).
- `PHASE-*.md`: Nhật ký phát triển và thiết kế hệ thống theo từng giai đoạn.
