/** Cấu hình production. Đổi `apiUrl` thành tên miền thật khi deploy. */
export const environment = {
  production: true,
  apiUrl: '/api',

  /**
   * Xem chú thích dài ở `environment.ts`. Tóm tắt: đây là giá trị **công
   * khai**, không phải secret; private key của FCM nằm ở server và không bao
   * giờ đi qua file này. Để rỗng thì tính năng push tự tắt, không đăng ký
   * token giả.
   */
  firebase: {
    apiKey: '',
    projectId: '',
    messagingSenderId: '',
    appId: '',
    vapidKey: '',
  },
};
