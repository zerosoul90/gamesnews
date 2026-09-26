import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { CaiDatThongBao } from '../../services/user.service';
import { duongDanCoThat } from '../../routes.spec-util';
import { NotificationSettingsComponent } from './notification-settings.component';

const GOC = 'http://api.test';
const URL = `${GOC}/api/v1/user/notification-settings`;

function macDinh(): CaiDatThongBao {
  return {
    quiet_hours: { from: '22:00', to: '07:00' },
    channels: { price_alert: true, streamer_live: true, forum_reply: true, news_digest: 'daily' },
  };
}

describe('NotificationSettingsComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<NotificationSettingsComponent>;
  let daDangNhap = true;

  beforeEach(() => {
    daDangNhap = true;
    TestBed.configureTestingModule({
      imports: [NotificationSettingsComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        { provide: AuthService, useValue: { isLoggedIn: () => daDangNhap } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NotificationSettingsComponent);
  });

  afterEach(() => http.verify());

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  /** `ngModel` gắn giá trị bất đồng bộ — phải chờ một nhịp mới đọc DOM được. */
  function mo(caiDat: CaiDatThongBao = macDinh()): void {
    fixture.detectChanges();
    http.expectOne(URL).flush(caiDat);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();
  }

  it('chưa đăng nhập: mời đăng nhập bằng link thật, không gọi API', () => {
    daDangNhap = false;
    fixture.detectChanges();

    http.expectNone(URL);
    const a = el().querySelector('a[href]');
    expect(duongDanCoThat(a?.getAttribute('href') ?? '')).toBeTrue();
  });

  it('hiện đúng trạng thái đã lưu của từng công tắc', fakeAsync(() => {
    const c = macDinh();
    c.channels.streamer_live = false;
    mo(c);

    const hop = (khoa: string) => el().querySelector<HTMLInputElement>(`input[data-kenh="${khoa}"]`)!;
    expect(hop('price_alert').checked).toBeTrue();
    expect(hop('streamer_live').checked).toBeFalse();
    expect(hop('forum_reply').checked).toBeTrue();
    // Không có nhãn thì trình đọc màn hình đọc "on" — đo được trên trình duyệt thật.
    expect(hop('streamer_live').getAttribute('aria-label')).toBe('Streamer lên sóng');
  }));

  it('lưu gửi cả khối cài đặt đã sửa, rồi báo đã lưu', fakeAsync(() => {
    mo();
    const hop = el().querySelector<HTMLInputElement>('input[data-kenh="forum_reply"]')!;
    hop.click();
    fixture.detectChanges();
    tick();

    fixture.componentInstance.luu();
    const req = http.expectOne(URL);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.channels.forum_reply).toBeFalse();
    expect(req.request.body.quiet_hours).toEqual({ from: '22:00', to: '07:00' });
    req.flush(req.request.body);
    fixture.detectChanges();

    expect(el().querySelector('[role="status"]')?.textContent).toContain('Đã lưu');
  }));

  it('sửa tiếp sau khi lưu thì dòng "đã lưu" biến mất', fakeAsync(() => {
    mo();
    fixture.componentInstance.luu();
    http.expectOne(URL).flush(macDinh());
    fixture.detectChanges();
    expect(fixture.componentInstance.daLuu).toBeTrue();

    el().querySelector<HTMLInputElement>('input[data-kenh="price_alert"]')!.click();
    fixture.detectChanges();
    tick();

    expect(fixture.componentInstance.daLuu).toBeFalse();
  }));

  it('chọn "Không nhận" bản tin thì cảnh báo thông báo đã gom sẽ bị bỏ', fakeAsync(() => {
    const c = macDinh();
    c.channels.news_digest = 'none';
    mo(c);

    expect(el().querySelector('[data-canh-bao-none]')?.textContent).toContain('bị bỏ');
  }));

  it('giờ sai định dạng: câu báo lỗi đọc được', fakeAsync(() => {
    mo();
    fixture.componentInstance.luu();
    http.expectOne(URL).flush({ detail: [] }, { status: 422, statusText: 'x' });
    fixture.detectChanges();

    expect(el().querySelector('[role="alert"]')?.textContent).toContain('HH:MM');
  }));
});
