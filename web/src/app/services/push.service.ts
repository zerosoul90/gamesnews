import { Inject, Injectable, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Observable, firstValueFrom } from 'rxjs';

import { API_BASE_URL } from '../api-base-url';
import { environment } from '../../environments/environment';

/** Vì sao chưa bật được push. Giao diện hiển thị đúng lý do, không gộp hết
 *  thành một câu "không khả dụng" — bốn ca dưới đây cần bốn hành động khác
 *  nhau từ phía người dùng, và ba trong số đó họ tự sửa được. */
export type LyDoKhongBat =
  | 'chua-cau-hinh'
  | 'trinh-duyet-khong-ho-tro'
  | 'bi-tu-choi'
  | null;

export interface KetQuaDangKy {
  ok: boolean;
  lyDo: LyDoKhongBat;
}

@Injectable({
  providedIn: 'root',
})
export class PushService {
  private readonly deviceUrl: string;
  private readonly laTrinhDuyet: boolean;

  constructor(
    private http: HttpClient,
    @Inject(API_BASE_URL) apiBaseUrl: string,
    @Inject(PLATFORM_ID) platformId: object,
  ) {
    this.deviceUrl = `${apiBaseUrl}/api/v1/user/device`;
    this.laTrinhDuyet = isPlatformBrowser(platformId);
  }

  /**
   * Đã có đủ cấu hình Firebase chưa.
   *
   * Kiểm **cả** `vapidKey`: thiếu riêng nó thì `getToken()` vẫn chạy nhưng trả
   * về token mà FCM không nhận cho web push — hỏng ở tận chặng gửi, tức xa
   * nhất khỏi chỗ gây ra lỗi.
   */
  get daCauHinh(): boolean {
    const c = environment.firebase;
    return Boolean(c.apiKey && c.projectId && c.messagingSenderId && c.appId && c.vapidKey);
  }

  /** Trình duyệt có đủ hai thứ push cần: service worker và Notification API. */
  get trinhDuyetHoTro(): boolean {
    return (
      this.laTrinhDuyet && 'serviceWorker' in navigator && typeof Notification !== 'undefined'
    );
  }

  /** Người dùng đã từ chối trước đó — trình duyệt sẽ không hỏi lại. */
  get daTuChoi(): boolean {
    return this.trinhDuyetHoTro && Notification.permission === 'denied';
  }

  /** Lý do không bật được, hoặc `null` nếu bật được. */
  get lyDoKhongBat(): LyDoKhongBat {
    if (!this.trinhDuyetHoTro) return 'trinh-duyet-khong-ho-tro';
    if (!this.daCauHinh) return 'chua-cau-hinh';
    if (this.daTuChoi) return 'bi-tu-choi';
    return null;
  }

  /**
   * Xin quyền, lấy token FCM, rồi đăng ký với server.
   *
   * **Không đăng ký gì khi chưa đủ điều kiện.** Gửi một chuỗi bịa lên
   * `/device` là làm hỏng chính thứ mình đang dựng: `tokens_of()` sẽ trả về
   * nó, `send_push_notification` đếm nó là một thiết bị, và mọi tầng phía trên
   * tin rằng người dùng có máy nhận thông báo. Đó là lỗi `MockFirebaseMessaging`
   * bên Flutter đang mắc, không lặp lại ở đây.
   */
  async dangKyThietBi(): Promise<KetQuaDangKy> {
    const lyDo = this.lyDoKhongBat;
    if (lyDo !== null) {
      return { ok: false, lyDo };
    }

    const quyen = await Notification.requestPermission();
    if (quyen !== 'granted') {
      return { ok: false, lyDo: 'bi-tu-choi' };
    }

    const token = await this.layToken();
    if (!token) {
      return { ok: false, lyDo: 'chua-cau-hinh' };
    }

    await firstValueFrom(this.guiToken(token));
    return { ok: true, lyDo: null };
  }

  /**
   * Nạp Firebase SDK và lấy token.
   *
   * `import()` động chứ không import tĩnh, vì hai lý do: SDK chỉ chạy được ở
   * trình duyệt (SSR sẽ nổ khi chạm `navigator`), và nó nặng — người không bật
   * thông báo thì không nên phải tải.
   */
  private async layToken(): Promise<string | null> {
    const { initializeApp } = await import('firebase/app');
    const { getMessaging, getToken } = await import('firebase/messaging');

    const app = initializeApp(environment.firebase);
    const messaging = getMessaging(app);

    const dangKy = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
    return getToken(messaging, {
      vapidKey: environment.firebase.vapidKey,
      serviceWorkerRegistration: dangKy,
    });
  }

  /** `device_type: 'web'` — backend khai `Literal["android","ios","web"]`. */
  guiToken(token: string): Observable<{ status: string; is_new_device: boolean }> {
    return this.http.post<{ status: string; is_new_device: boolean }>(this.deviceUrl, {
      fcm_token: token,
      device_type: 'web',
    });
  }

  /** Gỡ thiết bị. Backend nhận body y hệt lúc đăng ký. */
  goThietBi(token: string): Observable<{ status: string; removed: number }> {
    return this.http.delete<{ status: string; removed: number }>(this.deviceUrl, {
      body: { fcm_token: token, device_type: 'web' },
    });
  }
}
