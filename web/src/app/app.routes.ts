import { Routes } from '@angular/router';
import { DealComponent } from './pages/deal/deal.component';
import { FreeComponent } from './pages/free/free.component';
import { GameComponent } from './pages/game/game.component';
import { NewsComponent } from './pages/news/news.component';
import { NotFoundComponent } from './pages/not-found/not-found.component';
import { HomeComponent } from './pages/home/home.component';
import { StatsComponent } from './pages/stats/stats.component';
import { AuthComponent } from './pages/auth/auth.component';
import { WatchlistComponent } from './pages/watchlist/watchlist.component';
import { UserProfileComponent } from './pages/user-profile/user-profile.component';
import { FollowsComponent } from './pages/follows/follows.component';
import { WrappedComponent } from './pages/wrapped/wrapped.component';

export const routes: Routes = [
    { path: '', component: HomeComponent, pathMatch: 'full' },
    { path: 'login', component: AuthComponent },
    { path: 'register', component: AuthComponent },
    { path: 'profile', component: UserProfileComponent },
    { path: 'watchlist', component: WatchlistComponent },
    { path: 'follows', component: FollowsComponent },
    { path: 'wrapped', component: WrappedComponent },
    { path: 'deals', component: DealComponent },
    { path: 'free', component: FreeComponent },
    { path: 'news', component: NewsComponent },
    { path: 'game/:slug', component: GameComponent },
    { path: 'search', component: SearchComponent },
    { path: 'thong-ke', component: StatsComponent },
    // Phải là route cuối: '**' khớp mọi thứ nên đặt trên sẽ che hết bên dưới.
    // Thiếu nó thì router ném NG04002 và SSR trả 200 kèm vỏ app rỗng — Chrome
    // DevTools tự probe '/.well-known/appspecific/com.chrome.devtools.json' là
    // đủ để thấy stack trace đó trong log container.
    { path: '**', component: NotFoundComponent },
];
