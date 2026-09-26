import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { ActivatedRoute, Params, Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';

import { SearchComponent } from './search.component';
import { SearchResponse, SearchService } from '../../services/search.service';

function traVe(soHit: number, total: number): SearchResponse {
  return {
    query: '',
    total,
    page: 1,
    per_page: 20,
    facets: {},
    hits: Array.from({ length: soHit }, (_, i) => ({
      id: `65f1a2b3c4d5e6f7081900${String(i).padStart(2, '0')}`,
      slug: `game-${i}`,
      titles: { primary: `Game ${i}`, vi: null, ja: null },
      platforms: ['pc'],
      genres: ['indie'],
      type: 'game',
      release_year: 2024,
      cover: null,
    })),
  };
}

/** Phân bố giống catalog thật: vài thể loại lớn, một đuôi dài lèo tèo. */
const SO_GAME: Record<string, number> = {
  indie: 28093,
  rpg: 6867,
  'role-playing': 939,
  'city-builder': 150,
  education: 66,
  mmorpg: 1,
};

/**
 * Trang tìm kiếm — ba ô lọc và đường đi của chúng qua URL.
 *
 * Hạng mục này được giao ở `HANDOFF-4.md` §4.1 kèm sẵn bốn cạm bẫy, rồi nộp về
 * **không một test nào** — lần thứ hai liên tiếp hạng mục chính không có spec.
 * File này chốt cả bốn, cộng một lỗi tìm ra lúc review.
 *
 * Cạm bẫy 3 trong tài liệu ("hiện 1000+ khi `total` chạm trần Meilisearch")
 * không có ở đây vì nó vô nghĩa: `response.total` không được hiển thị ở đâu
 * cả, chỉ dùng trong hai điều kiện phân trang. Tài liệu viết hướng dẫn cho một
 * thành phần giao diện không tồn tại.
 */
describe('SearchComponent', () => {
  let fixture: ComponentFixture<SearchComponent>;
  let params$: BehaviorSubject<Params>;
  let timKiem: jasmine.Spy;
  let dieuHuong: jasmine.Spy;

  function dung(
    params: Params = {},
    soGame: Observable<Record<string, number>> = of(SO_GAME),
  ): void {
    params$ = new BehaviorSubject<Params>(params);
    timKiem = jasmine.createSpy('search').and.returnValue(of(traVe(0, 0)));

    TestBed.configureTestingModule({
      imports: [SearchComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ActivatedRoute, useValue: { queryParams: params$ } },
        { provide: SearchService, useValue: { search: timKiem, genreCounts: () => soGame } },
      ],
    });

    fixture = TestBed.createComponent(SearchComponent);
    dieuHuong = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture.detectChanges();
  }

  function oNam(): HTMLInputElement {
    return fixture.nativeElement.querySelector('input[type="number"]');
  }

  function goVao(o: HTMLInputElement, giaTri: string): void {
    o.value = giaTri;
    o.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  describe('lọc không cần từ khoá', () => {
    it('chỉ có thể loại, không có q, vẫn đi tìm', () => {
      dung({ genre: 'rpg' });

      // Backend cho `q` rỗng — đã đo `q=&genre=rpg` ra 1000 kết quả. Guard cũ
      // `if (!this.query.trim()) return` khiến chọn thể loại xong thấy trang
      // trắng.
      expect(timKiem).toHaveBeenCalled();
      expect(timKiem.calls.mostRecent().args[3]).toBeUndefined(); // platform
      expect(timKiem.calls.mostRecent().args[4]).toBe('rpg'); // genre
    });

    it('không từ khoá, không lọc nào thì không gọi API', () => {
      dung({});

      expect(timKiem).not.toHaveBeenCalled();
    });
  });

  describe('đồng bộ URL', () => {
    it('đổi select thì đưa page về 1 và giữ các lọc khác', () => {
      dung({ q: 'elden', platform: 'pc', page: '7' });

      fixture.componentInstance.genre = 'rpg';
      fixture.componentInstance.onFilterChange();

      const qp = dieuHuong.calls.mostRecent().args[1].queryParams;
      // Đang ở trang 7 của một tập lớn rồi lọc sang tập nhỏ thì trang 7 rỗng.
      expect(qp.page).toBe(1);
      expect(qp.q).toBe('elden');
      expect(qp.platform).toBe('pc');
      expect(qp.genre).toBe('rpg');
    });

    it('link phân trang mang theo cả ba bộ lọc', () => {
      dung({ q: 'elden', platform: 'pc', genre: 'rpg', year: '2024' });
      timKiem.and.returnValue(of(traVe(20, 100)));
      params$.next({ q: 'elden', platform: 'pc', genre: 'rpg', year: '2024' });
      fixture.detectChanges();

      const neo = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLAnchorElement>('a[href*="page="]'),
      );

      // Bản đầu dựng lại `queryParams` chỉ với `{q, page}`, nên bấm sang trang
      // 2 là mất sạch bộ lọc — lỗi chỉ lộ ra ở trang thứ hai.
      expect(neo.length).toBeGreaterThan(0);
      for (const a of neo) {
        expect(a.getAttribute('href')).toContain('platform=pc');
        expect(a.getAttribute('href')).toContain('genre=rpg');
        expect(a.getAttribute('href')).toContain('year=2024');
      }
    });
  });

  describe('ô năm', () => {
    it('gõ "2024" chỉ sinh một lần điều hướng, không phải bốn', fakeAsync(() => {
      dung({});

      for (const v of ['2', '20', '202', '2024']) {
        goVao(oNam(), v);
      }
      tick(300);

      // Đo trên bản chưa sửa: 4 lần `navigate` với year = 2, 20, 202, 2024.
      // Ba giá trị dở dang đều trả 0 kết quả nên người dùng thấy "không tìm
      // thấy" nháy ba lần, và phải bấm Back bốn lần mới rời được trang.
      expect(dieuHuong.calls.count()).toBe(1);
      expect(dieuHuong.calls.mostRecent().args[1].queryParams.year).toBe(2024);
    }));

    it('dừng gõ giữa chừng thì vẫn đi tìm bằng giá trị cuối', fakeAsync(() => {
      dung({});

      goVao(oNam(), '2019');
      tick(300);

      expect(dieuHuong.calls.count()).toBe(1);
      expect(dieuHuong.calls.mostRecent().args[1].queryParams.year).toBe(2019);
    }));
  });

  describe('nhãn và giá trị gửi lên', () => {
    it('option gửi slug, không gửi nhãn tiếng Việt', () => {
      dung({});
      const opts = Array.from(
        (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLOptionElement>('select option'),
      ).filter((o) => o.value !== '');

      const slugThat = [
        ...fixture.componentInstance.PLATFORMS.map((p) => p.slug),
        ...fixture.componentInstance.theLoai.map((g) => g.slug),
      ];

      // Backend so chuỗi nguyên văn: gửi "Nhập vai (RPG)" thay vì "rpg" thì ra
      // 0 kết quả, và không có lỗi nào để lần ra.
      for (const o of opts) {
        expect(slugThat).withContext(o.value).toContain(o.value);
      }
    });

    it('mọi lựa chọn đều có nhãn khác slug thô', () => {
      dung({});

      // Bản đầu dùng `{{ slug | titlecase }}` nên ra "Fps", "Mmorpg", "Crpg".
      // Chốt bằng hai mục hay lộ nhất.
      const nhan = fixture.componentInstance.theLoai.map((g) => g.label);
      expect(nhan).toContain('Nhập vai (role-playing)');
      expect(nhan).toContain('Nhập vai (RPG)');
      expect(fixture.componentInstance.PLATFORMS.map((p) => p.label)).toContain('Nintendo Switch');
    });
  });

  describe('dropdown thể loại dựng từ facet', () => {
    function slugTrongO(): string[] {
      const o = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
        'select[aria-label="Lọc theo thể loại"]',
      )!;
      return Array.from(o.options).map((x) => x.value).filter((v) => v !== '');
    }

    it('chỉ thể loại từ 100 game trở lên, nhiều game xếp trước', () => {
      dung({});

      // `education` (66) và `mmorpg` (1) là ngõ cụt: chọn vào gần như rỗng.
      expect(slugTrongO()).toEqual(['indie', 'rpg', 'role-playing', 'city-builder']);
    });

    it('thể loại đang chọn vẫn hiện dù dưới ngưỡng', () => {
      dung({ genre: 'mmorpg' });

      // Mở link cũ `?genre=mmorpg`: kết quả đã bị lọc, ô select không được
      // trống trơn như thể không có lọc nào.
      expect(slugTrongO()).toContain('mmorpg');
      expect(slugTrongO()).not.toContain('education');
    });

    it('slug chưa có nhãn vẫn lên dropdown, với nhãn dựng từ slug', () => {
      dung({});

      // Thiếu nhãn đẹp là chuyện nhỏ; lặng lẽ mất một thể loại 150 game mới
      // là chuyện lớn.
      const muc = fixture.componentInstance.theLoai.find((g) => g.slug === 'city-builder');
      expect(muc?.label).toBe('City builder');
    });

    it('không tải được facet thì trang vẫn tìm được', () => {
      spyOn(console, 'error');
      dung({ q: 'elden' }, throwError(() => new Error('503')));

      expect(fixture.componentInstance.theLoai).toEqual([]);
      expect(timKiem).toHaveBeenCalled();
    });
  });
});
