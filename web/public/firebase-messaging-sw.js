/* Service worker cho FCM web push.
 *
 * Phải nằm ở **gốc origin** (`/firebase-messaging-sw.js`) — thư mục `public/`
 * được copy nguyên vào gốc site nên file này ra đúng chỗ. Đặt sâu hơn thì
 * scope của service worker không phủ hết trang và FCM từ chối.
 *
 * Dùng `importScripts` với bản compat: service worker không phải module ES nên
 * không `import` được SDK dạng mới.
 *
 * CẤU HÌNH: các giá trị dưới đây phải khớp `environment.firebase`. Chúng là
 * giá trị công khai (xem chú thích ở `src/environments/environment.ts`) —
 * KHÔNG dán private key của FCM vào đây, file này ai cũng tải được.
 *
 * Để rỗng thì service worker không khởi tạo gì cả. Nó vẫn đăng ký được nhưng
 * im lặng, và `PushService` cũng đã chặn từ phía ứng dụng trước khi tới đây.
 */

importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');

const cauHinh = {
  apiKey: '',
  projectId: '',
  messagingSenderId: '',
  appId: '',
};

if (cauHinh.apiKey && cauHinh.projectId && cauHinh.messagingSenderId && cauHinh.appId) {
  firebase.initializeApp(cauHinh);
  const messaging = firebase.messaging();

  // Thông báo nhận khi tab đang đóng hoặc ở nền.
  messaging.onBackgroundMessage((payload) => {
    const title = (payload.notification && payload.notification.title) || 'GameNews';
    const body = (payload.notification && payload.notification.body) || '';

    // `data.game_id` do `services/notification.py` gắn vào. Dùng nó để bấm
    // thông báo là mở thẳng trang game, không phải trang chủ.
    const gameId = (payload.data && payload.data.game_id) || null;

    self.registration.showNotification(title, {
      body,
      icon: '/favicon.ico',
      data: { gameId },
    });
  });

  self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const gameId = event.notification.data && event.notification.data.gameId;
    const dich = gameId ? `/game/${gameId}` : '/';

    // Ưu tiên focus tab đang mở thay vì mở thêm tab mới mỗi lần bấm.
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then((danhSach) => {
        for (const c of danhSach) {
          if ('focus' in c) {
            c.navigate(dich);
            return c.focus();
          }
        }
        return clients.openWindow(dich);
      }),
    );
  });
}
