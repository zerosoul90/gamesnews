import { Routes } from '@angular/router';
import { DealComponent } from './pages/deal/deal.component';
import { FreeComponent } from './pages/free/free.component';
import { GameComponent } from './pages/game/game.component';
import { NewsComponent } from './pages/news/news.component';
import { NotFoundComponent } from './pages/not-found/not-found.component';
import { HomeComponent } from './pages/home/home.component';
import { StatsComponent } from './pages/stats/stats.component';
import { AuthComponent } from './pages/auth/auth.component';
import { SteamCallbackComponent } from './pages/auth/steam-callback.component';
import { AlertsComponent } from './pages/alerts/alerts.component';
import { UserProfileComponent } from './pages/user-profile/user-profile.component';
import { FollowsComponent } from './pages/follows/follows.component';
import { WrappedComponent } from './pages/wrapped/wrapped.component';
import { SearchComponent } from './pages/search/search.component';
import { LibraryComponent } from './pages/library/library.component';

export const routes: Routes = [
    { path: '', component: HomeComponent, pathMatch: 'full' },
    { path: 'login', component: AuthComponent },

    // Đích của `openid.return_to`. Đường dẫn này được ghép ở backend
    // (`app/api/auth.py`, `steam_login`) từ `FRONTEND_URL` — đổi một bên mà
    // quên bên kia thì Steam trả người dùng về trang 404 sau khi họ đã nhập
    // mật khẩu xong, tức lỗi chỉ lộ ra ở bước cuối cùng.
    { path: 'auth/steam/callback', component: SteamCallbackComponent },

    { path: 'profile', component: UserProfileComponent },
    { path: 'canh-bao-gia', component: AlertsComponent },
    { path: 'follows', component: FollowsComponent },
    { path: 'wrapped', component: WrappedComponent },
    { path: 'deals', component: DealComponent },
    { path: 'free', component: FreeComponent },
    { path: 'news', component: NewsComponent },
    { path: 'game/:slug', component: GameComponent },
    { path: 'search', component: SearchComponent },
    { path: 'thong-ke', component: StatsComponent },
    { path: 'thu-vien', component: LibraryComponent },

    // Phải là route cuối: '**' khớp mọi thứ nên đặt trên sẽ che hết bên dưới.
    // Thiếu nó thì router ném NG04002 và SSR trả 200 kèm vỏ app rỗng — Chrome
    // DevTools tự probe '/.well-known/appspecific/com.chrome.devtools.json' là
    // đủ để thấy stack trace đó trong log container.
    { path: '**', component: NotFoundComponent },
];
