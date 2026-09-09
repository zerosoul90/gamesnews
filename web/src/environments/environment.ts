/**
 * Cấu hình môi trường phát triển.
 *
 * `apiUrl` phải nằm ở một chỗ duy nhất. Viết cứng
 * `http://localhost:8000` trong từng service thì bản build production trỏ về
 * máy của người dùng cuối chứ không phải về server — và lỗi đó chỉ lộ ra sau
 * khi deploy, vì ở máy dev nó chạy đúng.
 */
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
};
