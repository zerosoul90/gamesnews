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

  /**
   * Cấu hình Firebase cho push trên web.
   *
   * **Những giá trị này KHÔNG phải secret.** Firebase web config và VAPID
   * *public* key nằm trong bundle của mọi trang dùng FCM — chúng định danh
   * project, không cấp quyền gì. Thứ phải giữ kín là `FCM_PRIVATE_KEY` phía
   * server (`app/core/config.py`), và nó không bao giờ đi qua đây. Đừng dán
   * private key vào file này.
   *
   * Để rỗng nghĩa là **chưa cấu hình**: `PushService` sẽ không xin quyền,
   * không lấy token, và không gọi `/device`. Đăng ký một token giả còn tệ hơn
   * không đăng ký gì — server sẽ tin là có thiết bị thật và gửi vào hư không.
   * Đó đúng là lỗi mà `MockFirebaseMessaging` bên Flutter đang mắc.
   *
   * Lấy giá trị ở Firebase Console → Project settings → General (web app) và
   * → Cloud Messaging → Web Push certificates (cho `vapidKey`).
   */
  firebase: {
    apiKey: '',
    projectId: '',
    messagingSenderId: '',
    appId: '',
    vapidKey: '',
  },
};
