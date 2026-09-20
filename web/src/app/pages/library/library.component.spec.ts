import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { LibraryComponent } from './library.component';
import { duongDanCoThat } from '../../routes.spec-util';

const GOC = 'http://api.test';

const THU_VIEN_RONG = { items: [], total: 0, limit: 50, offset: 0 };

/** Một trang phản hồi của `GET /api/v1/user/library`, đúng hình dạng backend
 *  trả: `{items[], total, limit, offset}` với `game` được phép `null`. */
function trang(soLuong: number, total: number, offset = 0) {
  return {
    items: Array.from({ length: soLuong }, (_, i) => ({
      game_id: `65f1a2b3c4d5e6f70819${String(offset + i).padStart(4, '0')}`,
      store: 'steam',
      playtime_minutes: 600 - (offset + i),
      synced_at: '2026-09-01T00:00:00+00:00',
      game: null,
    })),
    total,
    limit: 50,
    offset,
  };
}

/**
 * Trang thư viện Steam.
 *
 * Hai bất biến ở đây đều là lỗi đã xảy ra thật, không phải giả định.
 *
 * Một: **kết quả đồng bộ phải hiện ra.** Bản đầu gán
 * `dongBoKetQua = res` rồi gọi ngay `tai()`, mà `tai()` lại mở đầu bằng
 * `dongBoKetQua = null`. Hai việc chạy đồng bộ trong cùng một lượt, nên băng
 * rôn không hiện lần nào — kể cả ca `{synced: 0, skipped: N}`, đúng ca người
 * dùng cần được giải thích nhất.
 *
 * Hai: **liên kết đăng nhập phải tới được.** Bản đầu trỏ `/auth`, một đường
 * không có trong `app.routes.ts`, nên nút rơi vào route `**` và mở trang 404.
 * Build xanh, test xanh, chỉ người bấm mới biết.
 */
describe('LibraryComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<LibraryComponent>;
  let daDangNhap = true;

  beforeEach(() => {
    daDangNhap = true;
    TestBed.configureTestingModule({
      imports: [LibraryComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        { provide: AuthService, useValue: { isLoggedIn: () => daDangNhap } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(LibraryComponent);
  });

  afterEach(() => http.verify());

  /** Dựng trang ở trạng thái đã đăng nhập, mặc định thư viện rỗng. */
  function moTrang(duLieu: object = THU_VIEN_RONG): void {
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${GOC}/api/v1/user/library`).flush(duLieu);
    fixture.detectChanges();
  }

  function chu(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('giữ lại kết quả đồng bộ sau khi nạp lại danh sách', () => {
    moTrang();

    fixture.componentInstance.dongBo();
    http.expectOne(`${GOC}/api/v1/user/library/sync`).flush({ synced: 0, skipped: 3 });
    // `dongBo()` gọi `tai()` ngay trong nhánh `next` — chính lượt nạp lại này
    // từng xoá mất kết quả vừa gán.
    http.expectOne((r) => r.url === `${GOC}/api/v1/user/library`).flush(THU_VIEN_RONG);
    fixture.detectChanges();

    expect(fixture.componentInstance.dongBoKetQua).toEqual({ synced: 0, skipped: 3 });
    const chu = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(chu).toContain('Bỏ qua 3');
  });

  it('xoá thư viện thì gỡ luôn băng rôn đồng bộ của lượt trước', () => {
    moTrang();
    fixture.componentInstance.dongBo();
    http.expectOne(`${GOC}/api/v1/user/library/sync`).flush({ synced: 7, skipped: 0 });
    http.expectOne((r) => r.url === `${GOC}/api/v1/user/library`).flush(THU_VIEN_RONG);

    spyOn(window, 'confirm').and.returnValue(true);
    fixture.componentInstance.xoaThuVien();
    http.expectOne((r) => r.method === 'DELETE').flush({ deleted_count: 7 });

    // Để lại "đã đồng bộ 7 game" bên cạnh một thư viện rỗng là nói sai.
    expect(fixture.componentInstance.dongBoKetQua).toBeNull();
  });

  describe('phân trang', () => {
    it('tải thêm dùng offset bằng số game đã có và nối vào cuối', () => {
      moTrang(trang(50, 120));
      expect(fixture.componentInstance.conNua).toBeTrue();
      expect(chu()).toContain('Đang hiện 50 trong 120 game');

      fixture.componentInstance.taiThem();
      const req = http.expectOne(
        (r) => r.url === `${GOC}/api/v1/user/library` && r.params.get('offset') === '50',
      );
      expect(req.request.params.get('limit')).toBe('50');
      req.flush(trang(50, 120, 50));
      fixture.detectChanges();

      // Nối, không thay thế. Trước bản này trang chỉ gọi đúng một lần với
      // `offset=0`, nên 70 game còn lại không có đường nào tới được.
      expect(fixture.componentInstance.items.length).toBe(100);
      expect(chu()).toContain('Đang hiện 100 trong 120 game');
    });

    it('trang cuối vừa tròn một trang thì không mời bấm thêm', () => {
      // Ca mà cách "so độ dài trang với limit" làm sai: 50 game, đủ một trang
      // chẵn, nhưng không còn gì phía sau.
      moTrang(trang(50, 50));

      expect(fixture.componentInstance.conNua).toBeFalse();
      expect(chu()).not.toContain('Tải thêm');
    });

    it('tải thêm hỏng thì giữ nguyên phần đã tải được', () => {
      moTrang(trang(50, 120));

      fixture.componentInstance.taiThem();
      http
        .expectOne((r) => r.params.get('offset') === '50')
        .flush(null, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(fixture.componentInstance.items.length).toBe(50);
      expect(fixture.componentInstance.loi).toContain('Không tải thêm được');
    });

    it('không bắn request thứ hai khi đã tải hết', () => {
      moTrang(trang(30, 30));

      fixture.componentInstance.taiThem();

      // `conNua` sai mà vẫn gọi thì backend nhận `offset` vượt quá `total` và
      // trả mảng rỗng — vô hại nhưng là một vòng khứ hồi thừa mỗi lần bấm.
      http.expectNone(() => true);
    });
  });

  it('nút đăng nhập trỏ tới một route có thật', () => {
    daDangNhap = false;
    fixture.detectChanges();

    const neo = (fixture.nativeElement as HTMLElement).querySelector('a[href]');
    const dich = neo?.getAttribute('href') ?? '';

    expect(dich).toBe('/login');
    // Khẳng định thứ hai mới là cái bắt được lỗi cũ: `/auth` cũng là một chuỗi
    // trông hợp lệ, nhưng không khớp route nào ngoài `**`.
    expect(duongDanCoThat(dich)).toBeTrue();
  });

  it('profile riêng tư hiện hướng dẫn, không phải lỗi chung chung', () => {
    moTrang();

    fixture.componentInstance.dongBo();
    http
      .expectOne(`${GOC}/api/v1/user/library/sync`)
      .flush({ detail: 'PROFILE_IS_PRIVATE' }, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();

    expect(fixture.componentInstance.loiPrivateProfile).toBeTrue();
    // Gộp vào `loi` thì người dùng đọc "Thử lại sau" và thử lại mãi mãi: đây
    // là ca họ phải tự đổi cài đặt bên Steam mới xong.
    expect(fixture.componentInstance.loi).toBeNull();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Chi tiết trò chơi');
  });

});
