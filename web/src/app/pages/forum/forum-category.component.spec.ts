import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { BehaviorSubject } from 'rxjs';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { ChuDeTomTat, TrangThaiDang } from '../../services/forum.service';
import { duongDanCoThat } from '../../routes.spec-util';
import { ForumCategoryComponent } from './forum-category.component';

const GOC = 'http://api.test';
const F = `${GOC}/api/v1/forum`;

const CHUYEN_MUC = [{ slug: 'hoi-dap', name: 'Hỏi đáp & hỗ trợ', description: 'Lỗi, cấu hình máy', thread_count: 45 }];

function chuDe(i: number): ChuDeTomTat {
  return {
    id: `65f1a2b3c4d5e6f7081900${String(i).padStart(2, '0')}`,
    title: `Chủ đề ${i}`,
    category: 'hoi-dap',
    game: null,
    author: { id: 'u', nickname: i === 0 ? null : 'Ai Đó' },
    reply_count: i,
    locked: false,
    created_at: '2026-09-26T09:00:00+00:00',
    last_post_at: '2026-09-26T10:00:00+00:00',
  };
}

describe('ForumCategoryComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ForumCategoryComponent>;
  let query$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let dieuHuong: jasmine.Spy;

  beforeEach(() => {
    query$ = new BehaviorSubject(convertToParamMap({}));
    TestBed.configureTestingModule({
      imports: [ForumCategoryComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: new BehaviorSubject(convertToParamMap({ slug: 'hoi-dap' })), queryParamMap: query$ },
        },
        { provide: AuthService, useValue: { isLoggedIn: () => true, currentUserValue: null } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    dieuHuong = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture = TestBed.createComponent(ForumCategoryComponent);
  });

  afterEach(() => http.verify());

  function mo(items: ChuDeTomTat[], total: number, trangThai: TrangThaiDang, page = 1): void {
    fixture.detectChanges();
    http.expectOne(`${F}/categories`).flush(CHUYEN_MUC);
    const req = http.expectOne((r) => r.url === `${F}/threads`);
    expect(req.request.params.get('category')).toBe('hoi-dap');
    expect(req.request.params.get('page')).toBe(String(page));
    req.flush({ items, total, page, per_page: 20 });
    fixture.detectChanges();
    http.expectOne(`${F}/me`).flush(trangThai);
    fixture.detectChanges();
  }

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  it('hiện tên chuyên mục và chủ đề; tác giả chưa đặt tên thì có nhãn thay', () => {
    mo([chuDe(0), chuDe(1)], 2, { nickname: 'Tôi', can_post: true, reason: null });

    expect(el().querySelector('h1')?.textContent).toContain('Hỏi đáp & hỗ trợ');
    expect(el().textContent).toContain('Chủ đề 1');
    // `nickname: null` không được in thành chữ "null".
    expect(el().textContent).not.toContain('null');
    expect(el().textContent).toContain('Người dùng');
  });

  it('nút tạo chủ đề chỉ hiện khi đăng được', () => {
    mo([], 0, { nickname: null, can_post: false, reason: 'cần đặt biệt danh trước khi đăng bài' });

    const nut = Array.from(el().querySelectorAll('button')).map((b) => b.textContent?.trim());
    expect(nut).not.toContain('Tạo chủ đề');
  });

  it('tạo chủ đề xong thì mở ngay chủ đề đó', () => {
    mo([], 0, { nickname: 'Tôi', can_post: true, reason: null });
    const c = fixture.componentInstance;

    c.tieuDe = 'Máy yếu chơi được không';
    c.noiDung = 'GTX 1050';
    c.guiChuDe();

    const req = http.expectOne(`${F}/threads`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ category: 'hoi-dap', title: 'Máy yếu chơi được không', body: 'GTX 1050' });
    req.flush({ id: 'abc' });
    expect(dieuHuong).toHaveBeenCalledWith(['/forum/t', 'abc']);
  });

  it('link phân trang giữ chuyên mục và tới route thật', () => {
    query$.next(convertToParamMap({ page: '2' }));
    mo(Array.from({ length: 20 }, (_, i) => chuDe(i)), 45, { nickname: 'Tôi', can_post: true, reason: null }, 2);

    const phanTrang = Array.from(el().querySelectorAll<HTMLAnchorElement>('a[href*="page="]')).map(
      (a) => a.getAttribute('href') ?? '',
    );
    expect(phanTrang).toEqual(['/forum/c/hoi-dap?page=1', '/forum/c/hoi-dap?page=3']);
    for (const a of Array.from(el().querySelectorAll('a[href]'))) {
      expect(duongDanCoThat(a.getAttribute('href') ?? '')).withContext(a.getAttribute('href') ?? '').toBeTrue();
    }
  });

  it('slug không tồn tại thì báo không tìm thấy', () => {
    fixture.detectChanges();
    http.expectOne(`${F}/categories`).flush(CHUYEN_MUC);
    http.expectOne((r) => r.url === `${F}/threads`).flush({ detail: 'x' }, { status: 404, statusText: 'x' });
    fixture.detectChanges();

    expect(el().textContent).toContain('Không tìm thấy chuyên mục');
    // Ô trạng thái được dựng trước khi biết slug có tồn tại không, nên `/me`
    // vẫn đi. Chờ tải xong mới dựng thì mỗi lần sang trang lại gọi `/me` —
    // đổi một request thừa ở trang lỗi lấy một request thừa ở mọi trang.
    http.match(`${F}/me`).forEach((r) => r.flush({ nickname: null, can_post: false, reason: 'x' }));
  });
});

describe('ForumCategoryComponent — chế độ game (/forum/g/:gameSlug)', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ForumCategoryComponent>;
  let dieuHuong: jasmine.Spy;
  const GAME_ID = '65f1a2b3c4d5e6f7081900ff';

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ForumCategoryComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: new BehaviorSubject(convertToParamMap({ gameSlug: 'elden-ring' })),
            queryParamMap: new BehaviorSubject(convertToParamMap({ page: '2' })),
          },
        },
        { provide: AuthService, useValue: { isLoggedIn: () => true, currentUserValue: null } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    dieuHuong = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture = TestBed.createComponent(ForumCategoryComponent);
  });

  afterEach(() => http.verify());

  function mo(): void {
    fixture.detectChanges();
    http
      .expectOne((r) => r.url === `${GOC}/games/by-slug/elden-ring`)
      .flush({ id: GAME_ID, slug: 'elden-ring', title: 'Elden Ring' });
    const req = http.expectOne((r) => r.url === `${F}/threads`);
    // URL mang slug cho dễ đọc, nhưng `/threads` lọc theo id — phải đổi đúng.
    expect(req.request.params.get('game_id')).toBe(GAME_ID);
    expect(req.request.params.has('category')).toBeFalse();
    req.flush({ items: Array.from({ length: 20 }, (_, i) => chuDe(i)), total: 45, page: 2, per_page: 20 });
    fixture.detectChanges();
    http.expectOne(`${F}/me`).flush({ nickname: 'Tôi', can_post: true, reason: null });
    fixture.detectChanges();
  }

  it('lọc theo id của game, tiêu đề là tên game, phân trang giữ khu của game', () => {
    mo();
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('h1')?.textContent).toContain('Thảo luận: Elden Ring');
    const phanTrang = Array.from(el.querySelectorAll('a[href*="page="]')).map((a) => a.getAttribute('href'));
    expect(phanTrang).toEqual(['/forum/g/elden-ring?page=1', '/forum/g/elden-ring?page=3']);
    for (const a of Array.from(el.querySelectorAll('a[href]'))) {
      expect(duongDanCoThat(a.getAttribute('href') ?? '')).withContext(a.getAttribute('href') ?? '').toBeTrue();
    }
  });

  it('chủ đề mới gắn vào game, không vào chuyên mục', () => {
    mo();
    const c = fixture.componentInstance;
    c.tieuDe = 'Build nào mạnh nhất';
    c.noiDung = 'Hỏi thật';
    c.guiChuDe();

    const req = http.expectOne((r) => r.method === 'POST' && r.url === `${F}/threads`);
    expect(req.request.body).toEqual({ game_id: GAME_ID, title: 'Build nào mạnh nhất', body: 'Hỏi thật' });
    req.flush({ id: 'moi' });
    expect(dieuHuong).toHaveBeenCalledWith(['/forum/t', 'moi']);
  });

  it('slug game không tồn tại thì báo không tìm thấy game', () => {
    fixture.detectChanges();
    http
      .expectOne((r) => r.url === `${GOC}/games/by-slug/elden-ring`)
      .flush({ detail: 'x' }, { status: 404, statusText: 'x' });
    http.match(`${F}/me`).forEach((r) => r.flush({ nickname: null, can_post: false, reason: 'x' }));
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Không tìm thấy game');
  });
});
