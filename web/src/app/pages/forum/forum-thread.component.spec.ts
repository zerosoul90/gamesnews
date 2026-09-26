import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Meta } from '@angular/platform-browser';
import { BehaviorSubject } from 'rxjs';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService } from '../../services/auth.service';
import { BaiTraLoi, TrangChuDe, TrangThaiDang } from '../../services/forum.service';
import { duongDanCoThat } from '../../routes.spec-util';
import { ForumThreadComponent, LY_DO_BAO_CAO } from './forum-thread.component';

const GOC = 'http://api.test';
const F = `${GOC}/api/v1/forum`;
const TOI = '65f1a2b3c4d5e6f708190001';
const NGUOI_KHAC = '65f1a2b3c4d5e6f708190002';
const THREAD = '65f1a2b3c4d5e6f708190a01';

const DANG_DUOC: TrangThaiDang = { nickname: 'Tôi', can_post: true, reason: null };

function bai(id: string, authorId: string, body = 'một bài', quote: BaiTraLoi['quote'] = null): BaiTraLoi {
  return {
    id,
    author: { id: authorId, nickname: authorId === TOI ? 'Tôi' : 'Người Khác' },
    body,
    quote,
    created_at: '2026-09-26T10:00:00+00:00',
    edited_at: null,
  };
}

function trang(over: Partial<TrangChuDe['thread']> = {}, posts: BaiTraLoi[] = [], total = posts.length): TrangChuDe {
  return {
    thread: {
      id: THREAD,
      title: 'Elden Ring có đáng mua?',
      category: 'hoi-dap',
      game: null,
      author: { id: NGUOI_KHAC, nickname: 'Người Khác' },
      reply_count: total,
      locked: false,
      created_at: '2026-09-26T09:00:00+00:00',
      last_post_at: '2026-09-26T10:00:00+00:00',
      body: 'nội dung',
      edited_at: null,
      ...over,
    },
    posts,
    total_posts: total,
    page: 1,
    per_page: 30,
  };
}

/**
 * Trang một chủ đề diễn đàn.
 *
 * Bất biến quan trọng nhất ở đây là **nội dung người dùng không bao giờ thành
 * HTML**: backend lưu text thuần và không lọc gì (`docs/FORUM.md`), nên nội
 * suy của Angular là lớp duy nhất đứng giữa một bài chứa `<img onerror>` và
 * trình duyệt người đọc. Đổi sang `[innerHTML]` "cho đẹp" là mở XSS ngay.
 */
describe('ForumThreadComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ForumThreadComponent>;
  let query$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let dieuHuong: jasmine.Spy;

  beforeEach(() => {
    query$ = new BehaviorSubject(convertToParamMap({}));
    TestBed.configureTestingModule({
      imports: [ForumThreadComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: new BehaviorSubject(convertToParamMap({ id: THREAD })), queryParamMap: query$ },
        },
        {
          provide: AuthService,
          useValue: { isLoggedIn: () => true, currentUserValue: { user_id: TOI, steam_id64: 'x' } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    dieuHuong = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture = TestBed.createComponent(ForumThreadComponent);
  });

  afterEach(() => http.verify());

  function mo(duLieu: TrangChuDe, trangThai: TrangThaiDang | null = DANG_DUOC): void {
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${F}/threads/${THREAD}`).flush(duLieu);
    fixture.detectChanges();
    // Ô trạng thái chỉ được dựng sau khi chủ đề tải xong.
    const me = http.expectOne(`${F}/me`);
    if (trangThai) {
      me.flush(trangThai);
    } else {
      me.flush({ detail: 'x' }, { status: 500, statusText: 'x' });
    }
    http
      .match(`${F}/categories`)
      .forEach((r) => r.flush([{ slug: 'hoi-dap', name: 'Hỏi đáp & hỗ trợ', description: '', thread_count: 1 }]));
    fixture.detectChanges();
  }

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function nut(chu: string): HTMLButtonElement[] {
    return Array.from(el().querySelectorAll('button')).filter((b) => b.textContent?.trim() === chu);
  }

  it('HTML trong bài hiện ra dưới dạng chữ, không thành phần tử', () => {
    const doc = '<img src=x onerror="window.__xss=1"><b>đậm</b>';
    mo(trang({ body: doc }, [bai('p1', NGUOI_KHAC, doc)]));

    const khoi = Array.from(el().querySelectorAll('[data-noi-dung]'));
    expect(khoi.length).toBe(2);
    for (const k of khoi) {
      expect(k.querySelector('img, b')).toBeNull();
      expect(k.textContent).toContain('<b>đậm</b>');
    }
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it('chủ đề bị ẩn/xoá/không có: báo không tìm thấy và noindex', () => {
    const meta = TestBed.inject(Meta);
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${F}/threads/${THREAD}`).flush({ detail: 'x' }, { status: 404, statusText: 'x' });
    fixture.detectChanges();

    expect(el().textContent).toContain('Không tìm thấy chủ đề');
    expect(meta.getTag('name="robots"')?.content).toBe('noindex');
  });

  it('chưa đăng được thì không có form trả lời, nút trích dẫn hay báo cáo', () => {
    mo(trang({}, [bai('p1', NGUOI_KHAC)]), { nickname: 'Tôi', can_post: false, reason: 'beta kín' });

    expect(el().querySelector('form[aria-label="Viết trả lời"]')).toBeNull();
    expect(nut('Trích dẫn').length).toBe(0);
    expect(nut('Báo cáo').length).toBe(0);
    // Lý do do backend viết, hiện nguyên văn.
    expect(el().querySelector('[data-ly-do]')?.textContent).toContain('beta kín');
  });

  it('chủ đề khoá thì không trả lời được dù có quyền', () => {
    mo(trang({ locked: true }));

    expect(el().querySelector('form[aria-label="Viết trả lời"]')).toBeNull();
    expect(el().textContent).toContain('Chủ đề đã khoá');
  });

  it('nút xoá chỉ hiện trên bài của chính mình, nút báo cáo thì ngược lại', () => {
    mo(trang({}, [bai('p1', TOI), bai('p2', NGUOI_KHAC)]));

    const cacBai = Array.from(el().querySelectorAll('li[id^="bai-"]'));
    const nutTrong = (li: Element) => Array.from(li.querySelectorAll('button')).map((b) => b.textContent?.trim());
    expect(nutTrong(cacBai[0])).toContain('Xoá');
    expect(nutTrong(cacBai[0])).not.toContain('Báo cáo');
    expect(nutTrong(cacBai[1])).not.toContain('Xoá');
    expect(nutTrong(cacBai[1])).toContain('Báo cáo');
    // Chủ đề là của người khác.
    expect(nut('Xoá chủ đề').length).toBe(0);
  });

  it('trả lời có trích dẫn gửi đúng quote_post_id', () => {
    mo(trang({}, [bai('p1', NGUOI_KHAC)]));
    const c = fixture.componentInstance;

    c.trich(c.baiTraLoi[0]);
    c.noiDung = 'đồng ý';
    c.guiTraLoi();

    const req = http.expectOne(`${F}/threads/${THREAD}/posts`);
    expect(req.request.body).toEqual({ body: 'đồng ý', quote_post_id: 'p1' });
    req.flush({ id: 'p2' });
    http.expectOne((r) => r.url === `${F}/threads/${THREAD}`).flush(trang());
    expect(c.trichBai).toBeNull();
    expect(c.noiDung).toBe('');
  });

  it('trả lời làm tràn trang thì chuyển sang trang cuối', () => {
    const day = Array.from({ length: 30 }, (_, i) => bai(`p${i}`, NGUOI_KHAC));
    mo(trang({}, day, 30));
    const c = fixture.componentInstance;

    c.noiDung = 'bài thứ 31';
    c.guiTraLoi();
    http.expectOne(`${F}/threads/${THREAD}/posts`).flush({ id: 'p31' });

    expect(dieuHuong).toHaveBeenCalledWith(['/forum/t', THREAD], { queryParams: { page: 2 } });
  });

  it('lỗi validate của Pydantic hiện thành câu đọc được, không phải [object Object]', () => {
    mo(trang());
    const c = fixture.componentInstance;

    c.noiDung = 'x';
    c.guiTraLoi();
    http.expectOne(`${F}/threads/${THREAD}/posts`).flush(
      { detail: [{ msg: 'Value error, nội dung không được trống', loc: ['body', 'body'] }] },
      { status: 422, statusText: 'x' },
    );

    expect(c.loiGui).toBe('nội dung không được trống');
  });

  it('báo cáo gửi lý do đã chọn; bài bị ẩn thì nạp lại', () => {
    mo(trang({}, [bai('p1', NGUOI_KHAC)]));
    const c = fixture.componentInstance;

    c.moBaoCao('post', 'p1');
    c.lyDoChon = LY_DO_BAO_CAO[1];
    c.guiBaoCao();

    const req = http.expectOne(`${F}/reports`);
    expect(req.request.body).toEqual({ target_type: 'post', target_id: 'p1', reason: LY_DO_BAO_CAO[1] });
    req.flush({ hidden: true });
    http.expectOne((r) => r.url === `${F}/threads/${THREAD}`).flush(trang());
    expect(c.thongBao).toContain('ẩn');
  });

  it('trích dẫn tới bài đã bị ẩn thì không lộ nội dung', () => {
    mo(trang({}, [bai('p2', NGUOI_KHAC, 'trả lời', { id: 'p1', author: null, body: null })]));

    const trich = el().querySelector('[data-trich-dan]');
    expect(trich?.textContent).toContain('đã bị xoá hoặc ẩn');
  });

  it('breadcrumb hiện tên chuyên mục, không phải slug thô', () => {
    mo(trang());

    expect(el().querySelector('nav')?.textContent).toContain('Hỏi đáp & hỗ trợ');
    expect(el().querySelector('nav')?.textContent).not.toContain('hoi-dap');
  });

  it('mọi liên kết trên trang đều tới route thật', () => {
    mo(trang({ game: { id: 'g', slug: 'elden-ring', title: 'Elden Ring' } }, [bai('p1', NGUOI_KHAC)], 40));

    const hrefs = Array.from(el().querySelectorAll('a[href]')).map((a) => a.getAttribute('href') ?? '');
    expect(hrefs.length).toBeGreaterThan(0);
    for (const h of hrefs) {
      expect(duongDanCoThat(h)).withContext(h).toBeTrue();
    }
  });
});
