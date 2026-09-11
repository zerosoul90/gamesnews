import { Routes } from '@angular/router';
import { DealComponent } from './pages/deal/deal.component';
import { FreeComponent } from './pages/free/free.component';
import { GameComponent } from './pages/game/game.component';
import { NotFoundComponent } from './pages/not-found/not-found.component';

export const routes: Routes = [
    // Không có trang chủ riêng, `/deals` là nội dung chính. Thiếu route này thì
    // `/` render ra vỏ app với `router-outlet` rỗng và vẫn trả 200 — người mở
    // localhost:4200 thấy trang trắng, phải tự gõ đường dẫn.
    //
    // `pathMatch: 'full'` là bắt buộc: mặc định của redirect là prefix match,
    // mà chuỗi rỗng là tiền tố của *mọi* URL, nên mọi trang sẽ nhảy về /deals.
    //
    // Full page load vào `/` không chạm tới đây — server.ts đã 302 trước khi
    // Angular kịp bootstrap. Route này phục vụ điều hướng trong app (router
    // link, `router.navigate([''])`), nơi không có request nào ra server.
    { path: '', redirectTo: 'deals', pathMatch: 'full' },
    { path: 'deals', component: DealComponent },
    { path: 'free', component: FreeComponent },
    { path: 'game/:slug', component: GameComponent },
    // Phải là route cuối: '**' khớp mọi thứ nên đặt trên sẽ che hết bên dưới.
    // Thiếu nó thì router ném NG04002 và SSR trả 200 kèm vỏ app rỗng — Chrome
    // DevTools tự probe '/.well-known/appspecific/com.chrome.devtools.json' là
    // đủ để thấy stack trace đó trong log container.
    { path: '**', component: NotFoundComponent },
];
