import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Subject, of } from 'rxjs';

import { GameComponent } from './game.component';
import { GameDetail, GameService } from '../../services/game.service';
import { CommunityService } from '../../services/community.service';
import { NewsService } from '../../services/news.service';
import { AlertService } from '../../services/alert.service';
import { AuthService } from '../../services/auth.service';
import { Follow, UserService } from '../../services/user.service';
import { StructuredDataService } from '../../services/structured-data.service';
import { SITE_ORIGIN } from '../../site-origin';
import { duongDanCoThat } from '../../routes.spec-util';

const GAME_MAU: GameDetail = {
  id: '65f1a2b3c4d5e6f708192a3b',
  slug: 'test-game',
  title: 'Test Game',
  title_primary: 'Test Game Primary',
  type: 'game',
  // Luôn `null` — xem chú thích ở `game.component.html`: `games.series` không
  // có writer nào, nên giá trị khác null không tồn tại trong dữ liệu thật.
  series: null,
  platforms: [],
  genres: [],
  developers: [],
  publishers: [],
  release_dates: [],
  is_live_service: false,
  current_season: null,
  cover_image_url: null,
  screenshots: [],
  system_requirements: { minimum: {}, recommended: {} },
  region_locked_vn: false,
  steam_appid: null,
  region: 'vn',
  prices: [],
  price_history: [],
  community_score: { is_hidden: false, average_score: null, review_count: 0 },
  steam_review: null,
  intl_prices: null,
  player_counts: [],
};

function follow(targetType: string, targetId: string): Follow {
  return { id: `follow-${targetId}`, target_type: targetType, target_id: targetId, target: null };
}

/**
 * Trang game — cụm nút theo dõi, và các liên kết nội bộ.
 *
 * Phần theo dõi studio được viết ở lượt 3 mà **không có test nào**: toàn bộ
 * `napTheoDoi`/`doiTheoDoi` được viết lại từ một mục đơn thành
 * `Record<string, …>` rồi giao đi, chưa từng chạy ngoài trình duyệt. File này
 * bù lại phần đó.
 *
 * Nút series từng nằm cạnh nút studio và đã bị gỡ: `series` là null trên cả
 * 38.721 game của catalog nên `*ngIf="g.series"` không bao giờ đúng. Fixture
 * ở đây giữ `series: null` đúng như dữ liệu thật — đừng đặt nó thành một chuỗi
 * để "test cho đủ", làm vậy là kiểm một trạng thái không tồn tại.
 */
describe('GameComponent', () => {
  let fixture: ComponentFixture<GameComponent>;
  let userService: {
    getFollows: jasmine.Spy;
    follow: jasmine.Spy;
    unfollow: jasmine.Spy;
  };

  /** Dựng trang với danh sách studio và trạng thái đăng nhập cho trước. */
  function dung(opts: { dangNhap: boolean; developers?: string[]; daTheoDoi?: Follow[] }): void {
    const game: GameDetail = { ...GAME_MAU, developers: opts.developers ?? [] };

    userService = {
      getFollows: jasmine
        .createSpy('getFollows')
        .and.returnValue(of({ follows: opts.daTheoDoi ?? [], total: 0 })),
      follow: jasmine.createSpy('follow').and.returnValue(of({ status: 'ok', followed: 'x' })),
      unfollow: jasmine.createSpy('unfollow').and.returnValue(of({ status: 'ok' })),
    };

    TestBed.configureTestingModule({
      imports: [GameComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => 'test-game' } } },
        },
        { provide: GameService, useValue: { getBySlug: () => of(game) } },
        {
          provide: CommunityService,
          useValue: { getReviews: () => of({ reviews: [], total: 0, limit: 20, offset: 0 }) },
        },
        { provide: NewsService, useValue: { getNews: () => of({ articles: [], total: 0 }) } },
        { provide: AlertService, useValue: { getAlerts: () => of({ alerts: [] }) } },
        {
          provide: AuthService,
          useValue: { isLoggedIn: () => opts.dangNhap, currentUser$: of(null) },
        },
        { provide: UserService, useValue: userService },
        { provide: SITE_ORIGIN, useValue: 'http://localhost' },
        StructuredDataService,
      ],
    });

    fixture = TestBed.createComponent(GameComponent);
    fixture.detectChanges();
  }

  function nut(targetId: string): HTMLButtonElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector(
      `button[data-theo-doi="${targetId}"]`,
    );
  }

  describe('theo dõi studio', () => {
    it('mỗi studio một nút, không gộp thành một dòng', () => {
      dung({ dangNhap: true, developers: ['FromSoftware', 'Bandai Namco'] });

      expect(nut('FromSoftware')).toBeTruthy();
      expect(nut('Bandai Namco')).toBeTruthy();
      expect(nut(GAME_MAU.id)).toBeTruthy();
    });

    it('không có studio nào thì không hiện nút nào', () => {
      dung({ dangNhap: true, developers: [] });

      expect((fixture.nativeElement as HTMLElement).querySelectorAll('button[data-theo-doi]').length)
        .toBe(1); // chỉ còn nút theo dõi game
    });

    it('bấm gửi đúng target_type "developer" và tên studio nguyên văn', () => {
      dung({ dangNhap: true, developers: ['FromSoftware'] });

      nut('FromSoftware')!.click();

      // Tên studio gửi nguyên văn: backend lưu đúng chuỗi này và `follows_of`
      // tra lại bằng chính nó. Encode hay đổi hoa thường là hỏng vòng khứ hồi.
      expect(userService.follow).toHaveBeenCalledWith('developer', 'FromSoftware');
    });

    it('studio đã theo dõi thì nút ở trạng thái đã bật, và bấm là gỡ', () => {
      dung({
        dangNhap: true,
        developers: ['FromSoftware'],
        daTheoDoi: [follow('developer', 'FromSoftware')],
      });

      expect(nut('FromSoftware')!.textContent).toContain('Đang theo dõi');

      nut('FromSoftware')!.click();

      // `POST /follows` là upsert và không trả `_id`, nên gỡ phải dùng `id`
      // đọc được từ `GET /follows`.
      expect(userService.unfollow).toHaveBeenCalledWith('follow-FromSoftware');
      expect(userService.follow).not.toHaveBeenCalled();
    });

    it('cờ bận chỉ khoá đúng nút vừa bấm', () => {
      dung({ dangNhap: true, developers: ['FromSoftware', 'Bandai Namco'] });

      // Giữ lời gọi ở trạng thái treo để quan sát được lúc đang bận — `of()`
      // hoàn tất ngay trong cùng một nhịp nên không thấy gì.
      const treo = new Subject<{ status: string; followed: string }>();
      userService.follow.and.returnValue(treo);

      nut('FromSoftware')!.click();
      fixture.detectChanges();

      // Một cờ dùng chung cho cả cụm sẽ khoá luôn nút kia — với game bốn studio
      // thì người dùng thấy rất rõ.
      expect(nut('FromSoftware')!.disabled).toBeTrue();
      expect(nut('Bandai Namco')!.disabled).toBeFalse();

      treo.next({ status: 'ok', followed: 'x' });
      treo.complete();
      fixture.detectChanges();

      expect(nut('FromSoftware')!.disabled).toBeFalse();
    });

    it('chưa đăng nhập thì không hiện nút nào và không hỏi /follows', () => {
      dung({ dangNhap: false, developers: ['FromSoftware'] });

      expect((fixture.nativeElement as HTMLElement).querySelectorAll('button[data-theo-doi]').length)
        .toBe(0);
      expect(userService.getFollows).not.toHaveBeenCalled();
    });
  });

  it('mọi liên kết nội bộ trên trang đều là route có thật', () => {
    dung({ dangNhap: false, developers: [] });

    const trong = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a[href^="/"]'),
    ).map((a) => a.getAttribute('href')!);

    // Duyệt HẾT, không chốt riêng một liên kết: bản trước chọn phần tử bằng
    // `a[routerLink="/login"]` rồi khẳng định chính giá trị vừa dùng để chọn là
    // route thật — một vòng lặp kín, không bắt được liên kết hỏng nào khác.
    expect(trong.length).toBeGreaterThan(0);
    for (const href of trong) {
      expect(duongDanCoThat(href)).withContext(href).toBeTrue();
    }
  });
});
