import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { TrangThaiDang } from '../../services/forum.service';
import { duongDanCoThat } from '../../routes.spec-util';
import { ForumTrangThaiComponent } from './forum-trang-thai.component';

const GOC = 'http://api.test';
const ME = `${GOC}/api/v1/forum/me`;

/** Ô trạng thái diễn đàn: bốn nấc cổng, theo đúng thứ tự backend kiểm. */
describe('ForumTrangThaiComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ForumTrangThaiComponent>;
  let daDangNhap = true;
  let phatRa: (TrangThaiDang | null)[];

  beforeEach(() => {
    daDangNhap = true;
    phatRa = [];
    TestBed.configureTestingModule({
      imports: [ForumTrangThaiComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        { provide: AuthService, useValue: { isLoggedIn: () => daDangNhap } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ForumTrangThaiComponent);
    fixture.componentInstance.doiTrangThai.subscribe((t) => phatRa.push(t));
  });

  afterEach(() => http.verify());

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  it('chưa đăng nhập: mời đăng nhập bằng link tới route thật, không gọi API', () => {
    daDangNhap = false;
    fixture.detectChanges();

    const a = el().querySelector('a[href]');
    expect(a?.textContent).toContain('đăng nhập');
    expect(duongDanCoThat(a?.getAttribute('href') ?? '')).toBeTrue();
    expect(phatRa).toEqual([null]);
    http.expectNone(ME);
  });

  it('chưa có biệt danh: hiện form; lưu xong thì báo trạng thái mới lên trang cha', () => {
    fixture.detectChanges();
    http.expectOne(ME).flush({ nickname: null, can_post: false, reason: 'cần đặt biệt danh trước khi đăng bài' });
    fixture.detectChanges();
    expect(el().querySelector('form')).not.toBeNull();

    fixture.componentInstance.bietDanh = 'Rồng Đen';
    fixture.componentInstance.luuBietDanh();
    const req = http.expectOne(`${GOC}/api/v1/forum/me/nickname`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ nickname: 'Rồng Đen' });
    req.flush({ nickname: 'Rồng Đen', can_post: true, reason: null });
    fixture.detectChanges();

    expect(el().querySelector('form')).toBeNull();
    expect(el().textContent).toContain('Rồng Đen');
    expect(phatRa.at(-1)).toEqual({ nickname: 'Rồng Đen', can_post: true, reason: null });
  });

  it('có biệt danh nhưng chưa được cấp quyền: hiện nguyên văn lý do của backend', () => {
    fixture.detectChanges();
    http.expectOne(ME).flush({ nickname: 'Rồng Đen', can_post: false, reason: 'diễn đàn đang beta kín' });
    fixture.detectChanges();

    expect(el().querySelector('[data-ly-do]')?.textContent).toContain('diễn đàn đang beta kín');
  });

  it('biệt danh trùng: hiện câu báo lỗi của backend', () => {
    fixture.detectChanges();
    http.expectOne(ME).flush({ nickname: null, can_post: false, reason: 'x' });
    fixture.componentInstance.bietDanh = 'tran.van';
    fixture.componentInstance.luuBietDanh();
    http
      .expectOne(`${GOC}/api/v1/forum/me/nickname`)
      .flush({ detail: 'biệt danh này đã có người dùng' }, { status: 409, statusText: 'x' });
    fixture.detectChanges();

    expect(el().querySelector('[role="alert"]')?.textContent).toContain('đã có người dùng');
  });

  it('không tải được trạng thái thì coi như chưa đăng được', () => {
    fixture.detectChanges();
    http.expectOne(ME).flush({}, { status: 500, statusText: 'x' });

    // Hiện nút đăng bài rồi để backend từ chối là trải nghiệm tệ hơn.
    expect(phatRa).toEqual([null]);
  });
});
