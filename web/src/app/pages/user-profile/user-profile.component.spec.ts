import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';

import { API_BASE_URL } from '../../api-base-url';
import { AuthService, SteamSession } from '../../services/auth.service';
import { UserProfileComponent } from './user-profile.component';

const GOC = 'http://api.test';
const PHIEN: SteamSession = {
  user_id: '65f1a2b3c4d5e6f708192a3b',
  steam_id64: '76561198000000000',
};

/**
 * Hình dạng THẬT của `GET /community/users/{id}/badges`.
 *
 * Chép từ `app/models/community.py::UserBadge` đi qua `jsonify_docs`: khoá là
 * `_id` (`jsonify` không đổi tên khoá), và ngoài ba trường dưới đây thì không
 * còn gì. Không `name`, không `description`, không `icon_url`.
 *
 * Nếu một ngày file này đỏ vì interface `Badge` không khớp — sửa interface,
 * đừng sửa hằng số này. Nó là bản sao của backend, không phải mong muốn của
 * frontend.
 */
const BADGES_THAT = [
  {
    _id: '000000000000000000000001',
    user_id: PHIEN.user_id,
    badge_type: 'reviewer',
    earned_at: '2026-09-01T10:00:00+00:00',
  },
];

/**
 * Trang cá nhân — phần huy hiệu.
 *
 * Bản đầu khai `Badge` có `name`, `description`, `icon_url` và bind thẳng vào
 * template. Không trường nào tồn tại, nên trang in ra một lưới ô xám: không
 * ảnh, tiêu đề rỗng, mô tả rỗng. `Badge[]` chỉ là kiểu lúc biên dịch nên
 * TypeScript không hề kêu, và JSON thật chưa từng được đối chiếu với nó.
 *
 * Đó đúng là lỗi `docs/HANDOFF-2.md` §0 đã dựng cả tài liệu để ngăn. File này
 * là chỗ đối chiếu ấy.
 */
describe('UserProfileComponent — huy hiệu', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<UserProfileComponent>;

  function dung(phien: SteamSession | null): void {
    TestBed.configureTestingModule({
      imports: [UserProfileComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: GOC },
        {
          provide: AuthService,
          useValue: { currentUser$: of(phien), isLoggedIn: () => phien !== null },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(UserProfileComponent);
  }

  afterEach(() => http.verify());

  it('huy hiệu hiện ra có chữ, không phải ô rỗng', () => {
    dung(PHIEN);
    fixture.detectChanges();

    http
      .expectOne(`${GOC}/community/users/${PHIEN.user_id}/badges`)
      .flush(BADGES_THAT);
    fixture.detectChanges();

    const the = (fixture.nativeElement as HTMLElement).querySelector('h3');
    // Với bản cũ (`{{ badge.name }}` trên một trường không tồn tại) ô này rỗng.
    expect(the?.textContent?.trim()).toBe('Người đánh giá');
    expect(fixture.componentInstance.badges[0].nhanLuc).toBe('2026-09-01T10:00:00+00:00');
  });

  it('loại huy hiệu chưa đặt nhãn thì hiện mã thô, không bỏ trống', () => {
    dung(PHIEN);
    fixture.detectChanges();

    http.expectOne(`${GOC}/community/users/${PHIEN.user_id}/badges`).flush([
      { ...BADGES_THAT[0], badge_type: 'wiki_editor' },
    ]);
    fixture.detectChanges();

    // Backend có thể trao một loại mà web chưa kịp biết tên. Hiện `wiki_editor`
    // thì xấu nhưng đúng, và chỉ ngay ra loại nào còn thiếu nhãn; để trống thì
    // lặp lại đúng lỗi vừa sửa.
    const the = (fixture.nativeElement as HTMLElement).querySelector('h3');
    expect(the?.textContent?.trim()).toBe('wiki_editor');
  });

  it('chưa đăng nhập thì không gọi API huy hiệu', () => {
    dung(null);
    fixture.detectChanges();

    // `user_id` lấy từ phiên. Không có phiên mà vẫn gọi thì đường dẫn thành
    // `/community/users/undefined/badges` và backend trả 400.
    http.expectNone(() => true);
    expect(fixture.componentInstance.badges).toEqual([]);
  });
});
