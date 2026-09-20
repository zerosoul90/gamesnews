import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { LibraryComponent } from './library.component';

const GOC = 'http://api.test';

const THU_VIEN_RONG = { items: [], total: 0, limit: 50, offset: 0 };

/**
 * Trang thư viện Steam.
 *
 * Bất biến chính: **kết quả đồng bộ phải hiện ra.** Bản đầu gán
 * `dongBoKetQua = res` rồi gọi ngay `tai()`, mà `tai()` lại mở đầu bằng
 * `dongBoKetQua = null`. Hai việc chạy đồng bộ trong cùng một lượt, nên băng
 * rôn không hiện lần nào — kể cả ca `{synced: 0, skipped: N}`, đúng ca người
 * dùng cần được giải thích nhất.
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

  /** Dựng trang ở trạng thái đã đăng nhập, thư viện rỗng. */
  function moTrang(): void {
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${GOC}/api/v1/user/library`).flush(THU_VIEN_RONG);
    fixture.detectChanges();
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
