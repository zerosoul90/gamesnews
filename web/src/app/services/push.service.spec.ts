import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../api-base-url';
import { PushService } from './push.service';
import { environment } from '../../environments/environment';

/**
 * Bất biến số một: **chưa cấu hình thì không đăng ký gì cả.**
 *
 * Đẩy một token bịa lên `/device` làm hỏng đúng thứ đang dựng — `tokens_of()`
 * sẽ trả về nó, `send_push_notification` đếm nó là một thiết bị thật, và mọi
 * tầng phía trên tin rằng người dùng có máy nhận thông báo. Đó là lỗi
 * `MockFirebaseMessaging` bên Flutter đang mắc (`getToken()` trả chuỗi cứng
 * `"mock_device_fcm_token_12345"`), và là lý do file này tồn tại.
 */
const GOC = 'http://api.test';

describe('PushService', () => {
  let http: HttpTestingController;
  let service: PushService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(PushService);
  });

  afterEach(() => http.verify());

  describe('khi chưa cấu hình Firebase', () => {
    it('daCauHinh là false với config rỗng', () => {
      // Trạng thái mặc định của repo: mọi trường đều rỗng.
      expect(environment.firebase.apiKey).toBe('');
      expect(service.daCauHinh).toBeFalse();
    });

    it('lyDoKhongBat nói rõ là chưa cấu hình', () => {
      // Trong Karma có `navigator.serviceWorker` và `Notification`, nên lý do
      // phải là cấu hình chứ không phải trình duyệt.
      expect(service.trinhDuyetHoTro).toBeTrue();
      expect(service.lyDoKhongBat).toBe('chua-cau-hinh');
    });

    it('dangKyThietBi KHÔNG gọi API và KHÔNG xin quyền', async () => {
      let daXinQuyen = false;
      const goc = Notification.requestPermission;
      // Nếu service xin quyền khi chưa cấu hình thì người dùng thấy hộp thoại
      // của trình duyệt rồi nhận về một lỗi — hỏi một câu vô nghĩa.
      (Notification as any).requestPermission = async () => {
        daXinQuyen = true;
        return 'granted';
      };

      try {
        const kq = await service.dangKyThietBi();

        expect(kq.ok).toBeFalse();
        expect(kq.lyDo).toBe('chua-cau-hinh');
        expect(daXinQuyen).toBeFalse();
        // `afterEach` gọi `http.verify()` — có request nào lọt ra là đỏ ở đó.
        http.expectNone(() => true);
      } finally {
        (Notification as any).requestPermission = goc;
      }
    });
  });

  describe('đường gửi token', () => {
    it('guiToken POST đúng /api/v1/user/device với device_type web', () => {
      service.guiToken('token-that-tu-firebase').subscribe();
      const req = http.expectOne(() => true);

      expect(req.request.method).toBe('POST');
      expect(req.request.url).toBe(`${GOC}/api/v1/user/device`);
      expect(req.request.body.fcm_token).toBe('token-that-tu-firebase');
      // Backend khai `Literal["android","ios","web"]`; gửi sai là 422.
      expect(req.request.body.device_type).toBe('web');
      req.flush({ status: 'ok', is_new_device: true });
    });

    it('goThietBi DELETE kèm body, không phải query string', () => {
      service.goThietBi('token-cu').subscribe();
      const req = http.expectOne(() => true);

      expect(req.request.method).toBe('DELETE');
      expect(req.request.url).toBe(`${GOC}/api/v1/user/device`);
      // `DELETE /device` của backend đọc `payload: DeviceRegistration` từ
      // **body**. Gửi qua query thì Pydantic trả 422.
      expect(req.request.body.fcm_token).toBe('token-cu');
      req.flush({ status: 'ok', removed: 1 });
    });
  });
});
