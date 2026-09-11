import { InjectionToken } from '@angular/core';

import { environment } from '../environments/environment';

/**
 * Base URL của API, tách khỏi `environment` vì SSR và browser không dùng chung
 * một địa chỉ: browser gọi từ máy người dùng, còn SSR gọi từ trong container.
 *
 * Mặc định là `environment.apiUrl` — đúng cho browser và cho cả SSR khi chạy
 * ngoài Docker. Bản chạy trong Compose ghi đè ở `app.config.server.ts`.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: () => environment.apiUrl,
});
