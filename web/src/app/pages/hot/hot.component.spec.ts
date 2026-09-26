import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { BehaviorSubject } from 'rxjs';

import { API_BASE_URL } from '../../api-base-url';
import { HotResponse } from '../../services/hot.service';
import { HotComponent } from './hot.component';

const GOC = 'http://api.test';

const MOT_GAME: HotResponse = {
  board: 'rising',
  computed_at: '2026-09-26T16:20:00+00:00',
  games: [
    {
      rank: 1,
      game_id: '65f1a2b3c4d5e6f708192a3b',
      game_details: { title: 'Tân Binh', slug: 'tan-binh', cover_image_url: null },
      ccu_now: 5000,
      score_absolute: 0.4,
      score_momentum: 0.3,
      price: { price_final: 99000, discount_percent: 50, is_historical_low: true },
    },
  ],
};

describe('HotComponent', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<HotComponent>;
  let query$: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  beforeEach(() => {
    query$ = new BehaviorSubject(convertToParamMap({}));
    TestBed.configureTestingModule({
      imports: [HotComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        { provide: ActivatedRoute, useValue: { queryParamMap: query$ } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(HotComponent);
  });

  afterEach(() => http.verify());

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  it('mặc định là bảng phổ biến', () => {
    fixture.detectChanges();

    const req = http.expectOne((r) => r.url === `${GOC}/hot`);
    expect(req.request.params.get('board')).toBe('popular');
    req.flush({ board: 'popular', computed_at: null, games: [] });
  });

  it('?bang=dang-len là bảng đang lên, và đổi query thì tải lại', () => {
    query$.next(convertToParamMap({ bang: 'dang-len' }));
    fixture.detectChanges();
    http.expectOne((r) => r.params.get('board') === 'rising').flush(MOT_GAME);

    query$.next(convertToParamMap({}));
    http.expectOne((r) => r.params.get('board') === 'popular').flush(MOT_GAME);
  });

  it('?bang= lạ thì rơi về bảng phổ biến, không gửi giá trị lạ sang API', () => {
    query$.next(convertToParamMap({ bang: 'trending' }));
    fixture.detectChanges();

    http.expectOne((r) => r.params.get('board') === 'popular').flush(MOT_GAME);
  });

  it('thẻ hiện tên Việt, số người chơi và giá VND', () => {
    query$.next(convertToParamMap({ bang: 'dang-len' }));
    fixture.detectChanges();
    http.expectOne(() => true).flush(MOT_GAME);
    fixture.detectChanges();

    const text = el().textContent ?? '';
    expect(text).toContain('Tân Binh');
    expect(text).toContain('5.000 người đang chơi');
    expect(text).toContain('99.000₫');
    expect(text).toContain('Đáy lịch sử');
  });

  it('bảng đang lên rỗng thì nói rõ, không hiện trang trắng', () => {
    query$.next(convertToParamMap({ bang: 'dang-len' }));
    fixture.detectChanges();
    http.expectOne(() => true).flush({ board: 'rising', computed_at: null, games: [] });
    fixture.detectChanges();

    expect(el().textContent).toContain('chưa có game nào tăng hạng');
  });
});
