import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../api-base-url';
import { AlertService } from './alert.service';
import { AuthService } from './auth.service';
import { CommunityService } from './community.service';
import { DashboardService } from './dashboard.service';
import { SearchService } from './search.service';
import { UserService } from './user.service';

/**
 * Mỗi service phải gọi đúng một đường dẫn backend **có thật**.
 *
 * Đây là lớp chắn cho đúng loại lỗi vừa phải dọn: một lượt làm việc dựng bảy
 * trang gọi `/auth/login`, `/auth/register`, `/me`, `/me/follows`,
 * `/me/watchlist`, `/me/wrapped` — không đường nào tồn tại, tất cả 404. Không
 * gì bắt được: bản build vẫn xanh, SSR vẫn trả HTTP 200 (component nuốt lỗi
 * vào một dòng `error:`), và trang chỉ hiện "Vui lòng đăng nhập" như thể đó là
 * trạng thái bình thường.
 *
 * `DUONG_DAN_THAT` chép từ `/openapi.json` của backend. Nó phải được cập nhật
 * bằng tay khi backend đổi route — nhưng cập nhật bằng tay một danh sách vẫn
 * hơn hẳn việc không có ai kiểm.
 */
const GOC = 'http://api.test';

/** Route thật, lấy từ `GET /openapi.json`. Tham số đường dẫn thay bằng `{}`. */
const DUONG_DAN_THAT = [
  '/api/v1/auth/steam/login',
  '/api/v1/auth/steam/callback',
  '/api/v1/user/alerts',
  '/api/v1/user/alerts/{}',
  '/api/v1/user/follows',
  '/api/v1/user/follows/{}',
  '/api/v1/user/library',
  '/api/v1/user/library/sync',
  '/api/v1/user/me/wrapped/{}',
  '/community/games/{}/reviews',
  '/community/games/{}/reviews/score',
  '/dashboard/stats',
  '/deals',
  '/free-games',
  '/games/by-slug/{}',
  '/games/{}/prices',
  '/games/{}/price-history',
  '/news',
  '/search',
];

/** Đổi id cụ thể trong đường dẫn thành `{}` để so với danh sách trên. */
function chuanHoa(url: string): string {
  const duongDan = url.replace(GOC, '');
  return duongDan
    .split('/')
    .map((doan) => (/^[0-9a-f]{24}$/i.test(doan) || /^\d+$/.test(doan) ? '{}' : doan))
    .join('/');
}

describe('service gọi đúng đường dẫn backend có thật', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  /** Chạy một lời gọi rồi khẳng định URL nó bắn ra nằm trong danh sách thật. */
  function kiem(chay: () => void): string {
    chay();
    const req = http.expectOne(() => true);
    const duongDan = chuanHoa(req.request.urlWithParams.split('?')[0]);
    expect(DUONG_DAN_THAT).toContain(duongDan);
    req.flush({});
    return duongDan;
  }

  it('UserService.getFollows -> /api/v1/user/follows', () => {
    const s = TestBed.inject(UserService);
    expect(kiem(() => s.getFollows().subscribe())).toBe('/api/v1/user/follows');
  });

  it('UserService.getWrapped đặt năm trong đường dẫn, không phải query', () => {
    const s = TestBed.inject(UserService);
    s.getWrapped(2026).subscribe();
    const req = http.expectOne(() => true);

    expect(req.request.url).toBe(`${GOC}/api/v1/user/me/wrapped/2026`);
    // `?year=` là cách gọi của bản cũ và backend không đọc nó.
    expect(req.request.params.has('year')).toBeFalse();
    req.flush({});
  });

  it('UserService.unfollow -> /api/v1/user/follows/{id}', () => {
    const s = TestBed.inject(UserService);
    expect(kiem(() => s.unfollow('65f1a2b3c4d5e6f708192a3b').subscribe())).toBe(
      '/api/v1/user/follows/{}',
    );
  });

  it('AlertService.getAlerts -> /api/v1/user/alerts', () => {
    const s = TestBed.inject(AlertService);
    expect(kiem(() => s.getAlerts().subscribe())).toBe('/api/v1/user/alerts');
  });

  it('AlertService.deleteAlert -> /api/v1/user/alerts/{id}', () => {
    const s = TestBed.inject(AlertService);
    expect(kiem(() => s.deleteAlert('65f1a2b3c4d5e6f708192a3b').subscribe())).toBe(
      '/api/v1/user/alerts/{}',
    );
  });

  it('AlertService.themCanhBao không gửi user_id', () => {
    const s = TestBed.inject(AlertService);
    s.themCanhBao('65f1a2b3c4d5e6f708192a3b').subscribe();
    const req = http.expectOne(() => true);

    expect(req.request.method).toBe('POST');
    expect(req.request.url).toBe(`${GOC}/api/v1/user/alerts`);
    // Chủ sở hữu tới từ JWT. Gửi kèm `user_id` là mời người đọc tin rằng
    // client chỉ định được chủ — backend bỏ qua nó.
    expect(Object.keys(req.request.body)).not.toContain('user_id');
    expect(req.request.body.condition).toBe('historical_low');
    req.flush({});
  });

  it('AlertService.themCanhBao gửi đúng below_price kèm ngưỡng', () => {
    const s = TestBed.inject(AlertService);
    s.themCanhBao('65f1a2b3c4d5e6f708192a3b', 'below_price', 199000).subscribe();
    const req = http.expectOne(() => true);

    expect(req.request.url).toBe(`${GOC}/api/v1/user/alerts`);
    expect(req.request.body.condition).toBe('below_price');
    expect(req.request.body.value).toBe(199000);
    // Chỉ chốt phần service KHÔNG bóp méo giá trị được truyền vào. Việc ô
    // `type=number` có trả số hay trả chuỗi là chuyện của `NumberValueAccessor`
    // và phải kiểm trên trình duyệt thật — test này không đi qua form nên đừng
    // đọc nó như một bảo chứng cho điều đó.
    expect(typeof req.request.body.value).toBe('number');
    expect(Object.keys(req.request.body)).not.toContain('user_id');
    req.flush({});
  });

  it('AlertService.themCanhBao gửi đúng discount_pct kèm ngưỡng', () => {
    const s = TestBed.inject(AlertService);
    s.themCanhBao('65f1a2b3c4d5e6f708192a3b', 'discount_pct', 50).subscribe();
    const req = http.expectOne(() => true);

    expect(req.request.url).toBe(`${GOC}/api/v1/user/alerts`);
    expect(req.request.body.condition).toBe('discount_pct');
    expect(req.request.body.value).toBe(50);
    expect(Object.keys(req.request.body)).not.toContain('user_id');
    req.flush({});
  });

  it('CommunityService -> /community/games/{id}/reviews', () => {
    const s = TestBed.inject(CommunityService);
    expect(kiem(() => s.getReviews('65f1a2b3c4d5e6f708192a3b').subscribe())).toBe(
      '/community/games/{}/reviews',
    );
  });

  it('DashboardService -> /dashboard/stats', () => {
    const s = TestBed.inject(DashboardService);
    expect(kiem(() => s.getStats().subscribe())).toBe('/dashboard/stats');
  });

  it('SearchService -> /search', () => {
    const s = TestBed.inject(SearchService);
    expect(kiem(() => s.search('elden').subscribe())).toBe('/search');
  });

  it('AuthService đổi tham số OpenID ở /api/v1/auth/steam/callback', () => {
    const s = TestBed.inject(AuthService);
    s.completeSteamLogin({
      'openid.mode': 'id_res',
      'openid.claimed_id': 'https://steamcommunity.com/openid/id/7656119',
    }).subscribe();
    const req = http.expectOne((r) => r.url.includes('steam/callback'));

    expect(req.request.url).toBe(`${GOC}/api/v1/auth/steam/callback`);
    // Chữ ký của Steam ký trên đúng tập tham số này; rơi mất một cái là hỏng
    // xác thực, và hỏng theo kiểu chỉ lộ ra ở lần đăng nhập thật.
    expect(req.request.params.get('openid.mode')).toBe('id_res');
    expect(req.request.params.get('openid.claimed_id')).toBe(
      'https://steamcommunity.com/openid/id/7656119',
    );
    req.flush({ access_token: 't', token_type: 'bearer', steam_id64: '7656119', user_id: 'u' });
  });

  it('AuthService.steamLoginUrl trỏ tới endpoint đăng nhập thật', () => {
    const s = TestBed.inject(AuthService);

    expect(s.steamLoginUrl()).toBe(`${GOC}/api/v1/auth/steam/login`);
    expect(DUONG_DAN_THAT).toContain(chuanHoa(s.steamLoginUrl()));
  });

  it('không service nào còn gọi nhóm /me/* đã chết', () => {
    // Chốt riêng cho sáu đường dẫn của lượt trước. Nếu ai đó dựng lại chúng,
    // test này đỏ trước khi kịp lên main.
    const daChet = ['/me', '/me/follows', '/me/watchlist', '/me/wrapped', '/auth/login', '/auth/register'];
    for (const duongDan of daChet) {
      expect(DUONG_DAN_THAT).not.toContain(duongDan);
    }
  });
});
