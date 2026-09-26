import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Meta } from '@angular/platform-browser';
import { BehaviorSubject } from 'rxjs';

import { API_BASE_URL } from '../../api-base-url';
import { duongDanCoThat } from '../../routes.spec-util';
import { ForumSearchComponent } from './forum-search.component';

const GOC = 'http://api.test';
const URL_TIM = `${GOC}/api/v1/forum/search`;

describe('ForumSearchComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<ForumSearchComponent>;
  let query$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let dieuHuong: jasmine.Spy;

  beforeEach(() => {
    query$ = new BehaviorSubject(convertToParamMap({}));
    TestBed.configureTestingModule({
      imports: [ForumSearchComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        { provide: ActivatedRoute, useValue: { queryParamMap: query$ } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    dieuHuong = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture = TestBed.createComponent(ForumSearchComponent);
  });

  afterEach(() => http.verify());

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  it('không có từ khoá thì không gọi API; trang luôn noindex', () => {
    fixture.detectChanges();

    http.expectNone(() => true);
    expect(TestBed.inject(Meta).getTag('name="robots"')?.content).toBe('noindex');
  });

  it('gõ không tìm theo từng phím — chỉ khi bấm tìm mới đổi URL', () => {
    fixture.detectChanges();
    const c = fixture.componentInstance;

    c.tuKhoa = 'l';
    c.tuKhoa = 'li';
    c.tuKhoa = '  lien quan  ';
    expect(dieuHuong).not.toHaveBeenCalled();

    c.tim();
    expect(dieuHuong).toHaveBeenCalledOnceWith(['/forum/tim-kiem'], { queryParams: { q: 'lien quan' } });
  });

  it('kết quả hiện, link phân trang giữ từ khoá và tới route thật', () => {
    query$.next(convertToParamMap({ q: 'lien quan', page: '2' }));
    fixture.detectChanges();
    const req = http.expectOne((r) => r.url === URL_TIM);
    expect(req.request.params.get('q')).toBe('lien quan');
    expect(req.request.params.get('page')).toBe('2');
    req.flush({
      items: [
        {
          id: '65f1a2b3c4d5e6f708190001',
          title: 'Liên Quân mùa mới',
          category: 'thao-luan-chung',
          game: null,
          author: { id: 'u', nickname: 'A' },
          reply_count: 3,
          locked: false,
          created_at: '2026-09-26T09:00:00+00:00',
          last_post_at: '2026-09-26T09:00:00+00:00',
        },
      ],
      total: 45,
      page: 2,
      per_page: 20,
    });
    fixture.detectChanges();

    expect(el().textContent).toContain('45 chủ đề khớp “lien quan”');
    const phanTrang = Array.from(el().querySelectorAll('a[href*="page="]')).map((a) => a.getAttribute('href'));
    expect(phanTrang).toEqual(['/forum/tim-kiem?q=lien%20quan&page=1', '/forum/tim-kiem?q=lien%20quan&page=3']);
    for (const a of Array.from(el().querySelectorAll('a[href]'))) {
      const href = a.getAttribute('href') ?? '';
      expect(duongDanCoThat(href)).withContext(href).toBeTrue();
    }
  });

  it('từ khoá quá ngắn: hiện câu báo lỗi của backend', () => {
    query$.next(convertToParamMap({ q: 'a' }));
    fixture.detectChanges();
    http
      .expectOne((r) => r.url === URL_TIM)
      .flush({ detail: 'từ khoá cần ít nhất 2 ký tự' }, { status: 422, statusText: 'x' });
    fixture.detectChanges();

    expect(el().querySelector('[role="alert"]')?.textContent).toContain('ít nhất 2 ký tự');
  });
});
