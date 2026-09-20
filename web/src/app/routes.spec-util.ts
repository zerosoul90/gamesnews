import { Route } from '@angular/router';

import { routes } from './app.routes';

/**
 * Một `routerLink` trong template có trỏ tới route thật hay không.
 *
 * **Vì sao cần.** Router của Angular không bao giờ báo lỗi vì một đường dẫn
 * sai: route `**` ở cuối `app.routes.ts` khớp mọi thứ, nên liên kết hỏng chỉ
 * lặng lẽ mở trang 404. Không có tầng nào bắt được — `routerLink` nhận chuỗi
 * bất kỳ, build vẫn xanh, SSR vẫn trả HTTP 200.
 *
 * Lỗi đã xảy ra thật: nút "Đăng nhập" ở trang game và trang thư viện trỏ
 * `/auth`, trong khi `app.routes.ts` chỉ khai `auth/steam/callback` dưới tiền
 * tố đó. Route đăng nhập thật là `/login`.
 *
 * Cố ý **không** tính `**` là khớp — đó chính là thứ cần phát hiện.
 */
export function duongDanCoThat(href: string): boolean {
  const duongDan = href.split('?')[0].split('#')[0].replace(/^\//, '');
  const thuc = duongDan.split('/');

  return routes.some((route: Route) => {
    if (route.path === undefined || route.path === '**') {
      return false;
    }
    const mau = route.path.split('/');
    if (mau.length !== thuc.length) {
      return false;
    }
    // `:slug` khớp mọi đoạn khác rỗng; đoạn tĩnh phải trùng từng ký tự.
    return mau.every((doan, i) => (doan.startsWith(':') ? thuc[i] !== '' : doan === thuc[i]));
  });
}
