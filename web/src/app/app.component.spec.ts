import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

import { AppComponent } from './app.component';
import { AuthService } from './services/auth.service';
import { duongDanCoThat } from './routes.spec-util';
import { By } from '@angular/platform-browser';

/**
 * Bản trước của file này là scaffold mặc định của `ng new` và **đã hỏng sẵn**:
 * nó đòi một `<h1>` chứa "Hello, web" trong khi `app.component.html` từ lâu chỉ
 * còn đúng `<router-outlet>`. Không ai thấy vì CI chưa chạy `ng test`.
 *
 * Nay vỏ app có thêm `<app-nav>`, nên smoke test kiểm đúng thứ đáng kiểm: thanh
 * điều hướng có mặt và trỏ tới cả ba trang. Thiếu nav thì `/free` và `/news`
 * không thể tới được nếu không gõ tay URL — đúng lỗi vừa sửa.
 *
 * `provideRouter([])` là bắt buộc: nav dùng `routerLink`, và thiếu provider thì
 * `detectChanges()` ném lỗi chứ không phải chỉ render thiếu.
 *
 * `provideHttpClient` cũng vậy kể từ khi nav đọc phiên đăng nhập qua
 * `AuthService` — service ấy tiêm `HttpClient`.
 */
describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  it('dựng được app', () => {
    const fixture = TestBed.createComponent(AppComponent);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('vỏ app có thanh điều hướng', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('app-nav')).toBeTruthy();
  });

  it('nav trỏ tới cả ba trang', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const duongDan = Array.from(compiled.querySelectorAll('a[href]')).map((a) =>
      a.getAttribute('href'),
    );

    expect(duongDan).toContain('/deals');
    expect(duongDan).toContain('/free');
    expect(duongDan).toContain('/news');
    
    // Check that all routes exist
    duongDan.forEach(href => {
      if (href) expect(duongDanCoThat(href)).toBeTrue();
    });
  });

  it('nav trỏ tới nhóm cá nhân khi đăng nhập và mở menu mobile', () => {
    // Stub AuthService
    const authServiceStub = {
      currentUser$: {
        subscribe: (fn: any) => {
          fn({ user_id: 'test_user', token: 'test_token' });
          return { unsubscribe: () => {} };
        }
      }
    };
    TestBed.overrideProvider(AuthService, { useValue: authServiceStub });
    
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    // Simulate opening mobile menu
    const navComponentNode = fixture.debugElement.query(By.css('app-nav'));
    navComponentNode.componentInstance.doiMenuMobile();
    fixture.detectChanges();

    const duongDan = Array.from(compiled.querySelectorAll('a[href]')).map((a) =>
      a.getAttribute('href'),
    );

    expect(duongDan).toContain('/canh-bao-gia');
    expect(duongDan).toContain('/follows');
    expect(duongDan).toContain('/thu-vien');
    expect(duongDan).toContain('/wrapped');

    // Assert using duongDanCoThat
    duongDan.forEach(href => {
      if (href) expect(duongDanCoThat(href)).toBeTrue();
    });
  });
});
