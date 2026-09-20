import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';

import { GameComponent } from './game.component';
import { GameService, GameDetail } from '../../services/game.service';
import { CommunityService } from '../../services/community.service';
import { NewsService } from '../../services/news.service';
import { AlertService } from '../../services/alert.service';
import { AuthService } from '../../services/auth.service';
import { UserService } from '../../services/user.service';
import { StructuredDataService } from '../../services/structured-data.service';
import { SITE_ORIGIN } from '../../site-origin';
import { duongDanCoThat } from '../../routes.spec-util';

describe('GameComponent', () => {
  let component: GameComponent;
  let fixture: ComponentFixture<GameComponent>;

  const mockGameDetail: GameDetail = {
    id: '123',
    slug: 'test-game',
    title: 'Test Game',
    title_primary: 'Test Game Primary',
    type: 'game',
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
    player_counts: []
  };

  beforeEach(async () => {
    const authServiceMock = {
      isLoggedIn: () => false, // Not logged in to show the login link
      currentUser$: of(null)
    };

    const gameServiceMock = {
      getBySlug: () => of(mockGameDetail)
    };

    const communityServiceMock = {
      getReviews: () => of({ reviews: [], total: 0, limit: 20, offset: 0 })
    };

    const newsServiceMock = {
      getNews: () => of({ articles: [], total: 0 })
    };

    const alertServiceMock = {
      getAlerts: () => of({ alerts: [] })
    };

    const userServiceMock = {
      getFollows: () => of({ follows: [] })
    };

    await TestBed.configureTestingModule({
      imports: [GameComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { paramMap: { get: () => 'test-game' } }
          }
        },
        { provide: GameService, useValue: gameServiceMock },
        { provide: CommunityService, useValue: communityServiceMock },
        { provide: NewsService, useValue: newsServiceMock },
        { provide: AlertService, useValue: alertServiceMock },
        { provide: AuthService, useValue: authServiceMock },
        { provide: UserService, useValue: userServiceMock },
        { provide: SITE_ORIGIN, useValue: 'http://localhost' },
        StructuredDataService
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(GameComponent);
    component = fixture.componentInstance;
    fixture.detectChanges(); // Trigger ngOnInit
  });

  it('liên kết đăng nhập có thật', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const loginLink = compiled.querySelector('a[routerLink="/login"]');
    expect(loginLink).toBeTruthy();
    const href = loginLink?.getAttribute('routerLink');
    if (href) {
        expect(duongDanCoThat(href)).toBeTrue();
    }
  });
});
