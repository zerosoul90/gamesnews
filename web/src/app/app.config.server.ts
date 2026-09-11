import { mergeApplicationConfig, ApplicationConfig } from '@angular/core';
import { provideServerRendering } from '@angular/platform-server';
import { appConfig } from './app.config';
import { API_BASE_URL } from './api-base-url';
import { environment } from '../environments/environment';

const serverConfig: ApplicationConfig = {
  providers: [
    provideServerRendering(),
    {
      // SSR chạy trong Node nên `localhost` là loopback của chính container,
      // không phải của host — API nằm ở service `app` của Compose. Biến
      // API_BASE_URL do Compose truyền vào trỏ thẳng qua mạng nội bộ
      // (`http://app:8000`), nhờ đó cũng không phụ thuộc APP_PORT vốn chỉ là
      // cổng map ra host. Không có biến thì rơi về cùng giá trị browser dùng,
      // đúng cho trường hợp chạy SSR ngoài Docker.
      provide: API_BASE_URL,
      useValue: process.env['API_BASE_URL'] || environment.apiUrl,
    },
  ],
};

export const config = mergeApplicationConfig(appConfig, serverConfig);
