import { ENVIRONMENT_INITIALIZER, EnvironmentProviders, inject, makeEnvironmentProviders } from '@angular/core';
import { Meta } from '@angular/platform-browser';
import { ResolveEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/**
 * Gỡ `<meta name="robots">` mỗi lần đổi trang, để trang nào cần `noindex` tự
 * đặt lại còn trang khác mặc định được index.
 *
 * Angular không tự dọn meta tag. Trước đây chỉ trang 404 tự gỡ trong
 * `ngOnDestroy`, nên đi từ tìm kiếm/đăng nhập/hồ sơ sang một trang cần index
 * vẫn mang `noindex`. Dọn ở component cũng không đủ: đi từ một game 404 sang
 * game khác thì router tái sử dụng component, `ngOnDestroy` không chạy.
 *
 * `ResolveEnd`: sau guard và resolver, trước khi trang mới được kích hoạt — nên
 * tag trang mới đặt trong constructor/`ngOnInit` không bị xoá mất. Bot không
 * bị ảnh hưởng vì mỗi URL đều tải mới qua SSR; đây là cho người dùng chia sẻ
 * hoặc công cụ đọc DOM phía client.
 */
export function provideMetaRobotsReset(): EnvironmentProviders {
  return makeEnvironmentProviders([
    {
      provide: ENVIRONMENT_INITIALIZER,
      multi: true,
      useValue: () => {
        const meta = inject(Meta);
        inject(Router)
          .events.pipe(filter((e) => e instanceof ResolveEnd))
          .subscribe(() => meta.removeTag("name='robots'"));
      },
    },
  ]);
}
