import { Routes } from '@angular/router';
import { DealComponent } from './pages/deal/deal.component';
import { NotFoundComponent } from './pages/not-found/not-found.component';
import { HomeComponent } from './pages/home/home.component';

/**
 * Chỉ ba trang nạp ngay: `/` (trang chủ), `/deals`
 * (trang đích thật của người mới vào) và 404. Mọi trang khác lazy.
 *
 * Trước đây cả 14 trang nằm trong bundle ban đầu: 541 kB, vượt ngưỡng cảnh báo
 * 500 kB của `angular.json`, và mọi khách vào trang deal đều tải luôn code của
 * trang thống kê, thư viện, Wrapped... mà phần lớn không bao giờ mở. SSR vẫn
 * trả HTML đầy đủ cho mọi trang — lazy chỉ đổi lúc nào JS của trang được tải.
 */
// `title` ở route: bốn trang dưới đây chưa từng tự đặt tiêu đề nên rơi về
// "Web" của `index.html` — hiện nguyên chữ đó trên tab trình duyệt và trong kết
// quả Google. Trang nào tự đặt bằng `Title.setTitle` thì vẫn thắng (chạy sau).
export const routes: Routes = [
    { path: '', component: HomeComponent, pathMatch: 'full' },
    { path: 'login', title: 'Đăng nhập - GameNews', loadComponent: () => import('./pages/auth/auth.component').then((m) => m.AuthComponent) },

    // Đích của `openid.return_to`. Đường dẫn này được ghép ở backend
    // (`app/api/auth.py`, `steam_login`) từ `FRONTEND_URL` — đổi một bên mà
    // quên bên kia thì Steam trả người dùng về trang 404 sau khi họ đã nhập
    // mật khẩu xong, tức lỗi chỉ lộ ra ở bước cuối cùng.
    { path: 'auth/steam/callback', loadComponent: () => import('./pages/auth/steam-callback.component').then((m) => m.SteamCallbackComponent) },

    { path: 'profile', title: 'Trang cá nhân - GameNews', loadComponent: () => import('./pages/user-profile/user-profile.component').then((m) => m.UserProfileComponent) },
    { path: 'canh-bao-gia', loadComponent: () => import('./pages/alerts/alerts.component').then((m) => m.AlertsComponent) },
    { path: 'follows', loadComponent: () => import('./pages/follows/follows.component').then((m) => m.FollowsComponent) },
    { path: 'wrapped', loadComponent: () => import('./pages/wrapped/wrapped.component').then((m) => m.WrappedComponent) },
    { path: 'deals', component: DealComponent },
    { path: 'hot', loadComponent: () => import('./pages/hot/hot.component').then((m) => m.HotComponent) },
    { path: 'free', loadComponent: () => import('./pages/free/free.component').then((m) => m.FreeComponent) },
    { path: 'news', loadComponent: () => import('./pages/news/news.component').then((m) => m.NewsComponent) },
    { path: 'game/:slug', loadComponent: () => import('./pages/game/game.component').then((m) => m.GameComponent) },
    { path: 'search', title: 'Tìm game - GameNews', loadComponent: () => import('./pages/search/search.component').then((m) => m.SearchComponent) },
    { path: 'thong-ke', title: 'Thống kê giá game - GameNews', loadComponent: () => import('./pages/stats/stats.component').then((m) => m.StatsComponent) },
    { path: 'thu-vien', loadComponent: () => import('./pages/library/library.component').then((m) => m.LibraryComponent) },
    {
      path: 'cai-dat-thong-bao',
      loadComponent: () =>
        import('./pages/notification-settings/notification-settings.component').then(
          (m) => m.NotificationSettingsComponent,
        ),
    },
    // Diễn đàn — `docs/FORUM.md`. `c/` và `t/` tách hai loại trang để slug
    // chuyên mục không bao giờ đụng id chủ đề.
    //
    // Lazy: nạp thẳng thì bundle ban đầu tăng 531 -> 567 kB cho mọi người vào
    // trang chủ, kể cả người không bao giờ mở diễn đàn.
    {
      path: 'forum',
      loadComponent: () => import('./pages/forum/forum-home.component').then((m) => m.ForumHomeComponent),
    },
    {
      path: 'forum/tim-kiem',
      loadComponent: () =>
        import('./pages/forum/forum-search.component').then((m) => m.ForumSearchComponent),
    },
    {
      path: 'forum/c/:slug',
      loadComponent: () =>
        import('./pages/forum/forum-category.component').then((m) => m.ForumCategoryComponent),
    },
    {
      path: 'forum/g/:gameSlug',
      loadComponent: () =>
        import('./pages/forum/forum-category.component').then((m) => m.ForumCategoryComponent),
    },
    {
      path: 'forum/t/:id',
      loadComponent: () =>
        import('./pages/forum/forum-thread.component').then((m) => m.ForumThreadComponent),
    },

    // Phải là route cuối: '**' khớp mọi thứ nên đặt trên sẽ che hết bên dưới.
    // Thiếu nó thì router ném NG04002 và SSR trả 200 kèm vỏ app rỗng — Chrome
    // DevTools tự probe '/.well-known/appspecific/com.chrome.devtools.json' là
    // đủ để thấy stack trace đó trong log container.
    { path: '**', component: NotFoundComponent },
];
