import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch } from '@angular/common/http';

import { routes } from './app.routes';
import { provideClientHydration, withNoHttpTransferCache } from '@angular/platform-browser';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    // `withNoHttpTransferCache`: transfer cache đang TRƯỢT 100%, nên nó chỉ là
    // gánh nặng. Khoá cache sinh từ URL request, mà SSR gọi
    // `http://app:8000/...` còn browser gọi `/api/...` — hai khoá khác nhau.
    // Quan sát trực tiếp trên Chrome: trang vẫn phát
    // `GET /api/games/by-slug/portal-2?history_days=30` sau khi hydrate, dù
    // response đã nằm sẵn trong khối `ng-state`.
    //
    // Cái giá của việc giữ nó: khối `ng-state` chiếm 4.278 bytes, tức 25,5%
    // trang /game/portal-2, và nhúng luôn tên host nội bộ `app:8000` vào page
    // source. Tắt đi là trang nhẹ hơn 1/4 mà số request không đổi.
    //
    // Muốn cache thật sự có tác dụng thì phải làm SSR và browser dùng CÙNG một
    // chuỗi URL — khi đó tiết kiệm được hẳn một round-trip. Nhưng cách đó buộc
    // SSR gọi qua origin công khai của chính nó, thêm một chặng qua Express của
    // nó và phụ thuộc việc container tự gọi được URL public của mình.
    provideClientHydration(withNoHttpTransferCache()),
    provideHttpClient(withFetch())
  ]
};
