import { DOCUMENT } from '@angular/common';
import { InjectionToken, inject } from '@angular/core';

/**
 * Origin công khai của trang, dạng `https://example.com` (không có `/` cuối).
 *
 * Dùng cho `og:image`, `og:url`, canonical — những URL bị **người khác** đọc:
 * crawler của Google, cache của Facebook. Chúng bắt buộc phải là URL tuyệt đối
 * và phải là địa chỉ người ngoài gọi được.
 *
 * KHÔNG dùng `API_BASE_URL` cho việc này. Lúc SSR giá trị đó là
 * `http://app:8000` — tên service trong mạng nội bộ Docker. Lấy nó làm `og:image`
 * là đẩy một URL không ai ngoài cluster phân giải được lên thẻ share, rồi
 * Facebook cache lại cái ảnh lỗi đó.
 *
 * Trên browser suy ra từ `location.origin`. Phía SSR không có `location`, nên
 * `server.ts` ghi đè bằng host của chính request — tự cấu hình, không phải nhớ
 * sửa một biến môi trường mỗi lần đổi tên miền.
 */
export const SITE_ORIGIN = new InjectionToken<string>('SITE_ORIGIN', {
  providedIn: 'root',
  factory: () => inject(DOCUMENT).location?.origin ?? '',
});
