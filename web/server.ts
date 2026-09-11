import { APP_BASE_HREF } from '@angular/common';
import { CommonEngine } from '@angular/ssr';
import express from 'express';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import bootstrap from './src/main.server';

/**
 * Gắn proxy `/api` -> backend.
 *
 * Bản production build cho `environment.apiUrl = '/api'`, tức browser gọi về
 * cùng origin với trang — không cần CORS, không nhúng cứng host backend vào
 * bundle. Nhưng Express này không biết `/api` là gì, nên thiếu proxy thì
 * `GET /api/deals` rơi xuống route SSR và trả về HTML; `HttpClient` nhận
 * `content-type: text/html` rồi chết lúc parse JSON. Lỗi đó chỉ lộ ra sau khi
 * deploy, vì bản development trỏ thẳng `http://localhost:8000` không qua đây.
 *
 * Đích lấy từ `API_BASE_URL` — cùng biến phía SSR dùng (`app.config.server.ts`).
 * Thiếu biến thì trả 502 kèm lời giải thích, chứ không im lặng trả HTML.
 */
function mountApiProxy(server: express.Express): void {
  const apiBaseUrl = process.env['API_BASE_URL'];

  if (!apiBaseUrl) {
    console.warn(
      'API_BASE_URL chưa đặt: /api sẽ trả 502. Bản production build gọi API qua ' +
        '/api nên cần biến này; xem service `web` trong docker-compose.yml.',
    );
    server.use('/api', (_req, res) => {
      res.status(502).json({ detail: 'API_BASE_URL chưa được cấu hình trên server SSR.' });
    });
    return;
  }

  const upstream = new URL(apiBaseUrl);
  const sendUpstream = upstream.protocol === 'https:' ? httpsRequest : httpRequest;
  // `new URL('http://app:8000').pathname` là '/', nối thẳng sẽ ra '//deals'.
  const basePath = upstream.pathname.replace(/\/$/, '');

  server.use('/api', (req, res) => {
    // Trong `use('/api', ...)`, `req.url` đã bị cắt mất '/api' và còn đúng phần
    // đuôi kèm query — khớp cách DealService dựng `${apiBaseUrl}/deals`.
    const proxied = sendUpstream(
      {
        protocol: upstream.protocol,
        hostname: upstream.hostname,
        port: upstream.port,
        path: `${basePath}${req.url}`,
        method: req.method,
        // Ghi đè `host`: giữ 'localhost:4200' thì backend nào route theo virtual
        // host sẽ không tìm ra ứng dụng.
        headers: { ...req.headers, host: upstream.host },
      },
      (upstreamRes) => {
        res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
        upstreamRes.pipe(res);
      },
    );

    proxied.on('error', (err) => {
      console.error(`proxy /api -> ${apiBaseUrl} lỗi:`, err.message);
      if (res.headersSent) {
        res.destroy();
      } else {
        res.status(502).json({ detail: 'Không gọi được backend.' });
      }
    });

    req.pipe(proxied);
  });
}

// The Express app is exported so that it can be used by serverless Functions.
export function app(): express.Express {
  const server = express();
  const serverDistFolder = dirname(fileURLToPath(import.meta.url));
  const browserDistFolder = resolve(serverDistFolder, '../browser');
  const indexHtml = join(serverDistFolder, 'index.server.html');

  const commonEngine = new CommonEngine();

  server.set('view engine', 'html');
  server.set('views', browserDistFolder);

  // Phải đứng trước `express.static` và route SSR: cả hai đều khớp '**' nên
  // `/api/deals` sẽ bị SSR render thành HTML nếu proxy gắn sau.
  mountApiProxy(server);

  // `/` -> `/deals` bằng 302 thật, không để router Angular tự redirect khi SSR.
  // Redirect phía client cũng ra đúng trang, nhưng HTML của `/deals` khi đó được
  // trả dưới URL `/` kèm status 200 — hai URL cùng nội dung, cùng `<title>`, nên
  // bot phải tự đoán bản nào là chuẩn. Chuyển hướng ở tầng HTTP thì chỉ còn một
  // URL canonical, và cũng không tốn một lượt render SSR cho trang bị bỏ đi.
  // Phải đứng trước `express.static`, vì `index: 'index.html'` sẽ nhận `/`.
  server.get('/', (_req, res) => {
    res.redirect(302, '/deals');
  });

  // Serve static files from /browser
  server.get('**', express.static(browserDistFolder, {
    maxAge: '1y',
    index: 'index.html',
  }));

  // All regular routes use the Angular engine
  server.get('**', (req, res, next) => {
    const { protocol, originalUrl, baseUrl, headers } = req;

    commonEngine
      .render({
        bootstrap,
        documentFilePath: indexHtml,
        url: `${protocol}://${headers.host}${originalUrl}`,
        publicPath: browserDistFolder,
        providers: [{ provide: APP_BASE_HREF, useValue: baseUrl }],
      })
      .then((html) => res.send(html))
      .catch((err) => next(err));
  });

  return server;
}

function run(): void {
  const port = process.env['PORT'] || 4000;

  // Start up the Node server
  const server = app();
  server.listen(port, () => {
    console.log(`Node Express server listening on http://localhost:${port}`);
  });
}

run();
