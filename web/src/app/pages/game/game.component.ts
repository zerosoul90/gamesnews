import { Component, Inject, OnInit, Optional } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { RENDER_STATUS, RenderStatus } from '../../render-status';
import { SITE_ORIGIN } from '../../site-origin';
import { GameDetail, GamePrice, GameService, PlayerCountDay } from '../../services/game.service';
import { StructuredDataService } from '../../services/structured-data.service';
import { CommunityService, Review } from '../../services/community.service';
import { NewsService, Article } from '../../services/news.service';
import { AlertService, PriceAlert } from '../../services/alert.service';
import { kiemNguongGia, kiemPhanTram } from './nguong';
import { AuthService } from '../../services/auth.service';
import { UserService, Follow } from '../../services/user.service';

/** Một cột của biểu đồ người chơi, toạ độ đã tính sẵn trong viewBox 100x40. */
interface PlayerBar {
  x: number;
  y: number;
  width: number;
  height: number;
  day: PlayerCountDay;
}

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './game.component.html',
  styleUrl: './game.component.css',
})
export class GameComponent implements OnInit {
  game: GameDetail | null = null;
  isLoading = true;
  notFound = false;

  // Dựng sẵn một lần, không gọi hàm trong `*ngFor`: hàm trả mảng mới mỗi lần
  // change detection chạy, nên ngFor phải diff lại toàn bộ danh sách mỗi vòng.
  minimumRows: { key: string; value: string }[] = [];
  recommendedRows: { key: string; value: string }[] = [];

  relatedNews: Article[] = [];
  reviews: Review[] = [];
  reviewsTotal = 0;

  /** Cảnh báo của chính game này, giữ nguyên bản ghi thay vì vài cờ rời.
   *
   *  Phải giữ cả `id`: backend xoá theo `_id` của cảnh báo chứ không theo
   *  `game_id`. Không giữ thì nút bấm chỉ bật được một chiều. */
  private canhBaoCuaGame: PriceAlert[] = [];
  dangDoiCanhBao = false;

  dangTheoDoi: Follow | null = null;
  dangDoiTheoDoi = false;

  // Form review
  reviewScore: number | null = null;
  reviewComment = '';
  dangGuiReview = false;
  loiReview: string | null = null;

  /** Một game có thể có nhiều cảnh báo ở các điều kiện khác nhau — khoá upsert
   *  của backend là `{user_id, game_id, condition}`. Nên tra theo `condition`,
   *  đừng giả định mỗi game một cảnh báo. */
  private canhBaoTheoDieuKien(condition: string): PriceAlert | null {
    return this.canhBaoCuaGame.find((a) => a.condition === condition) ?? null;
  }

  get canhBaoDay(): PriceAlert | null {
    return this.canhBaoTheoDieuKien('historical_low');
  }

  get canhBaoNguong(): PriceAlert | null {
    return this.canhBaoTheoDieuKien('below_price');
  }

  get canhBaoPhanTram(): PriceAlert | null {
    return this.canhBaoTheoDieuKien('discount_pct');
  }

  get daDatCanhBao(): boolean {
    return this.canhBaoDay !== null;
  }

  // --- form đặt ngưỡng ---
  //
  // Hai điều kiện nằm chung một bảng, mỗi cái một dòng có nút lưu/xoá riêng —
  // KHÔNG phải hai lựa chọn loại trừ nhau. Khoá upsert của backend là
  // `{user_id, game_id, condition}`, nên một game đặt được cả hai cùng lúc; làm
  // radio thì giao diện nói sai về chính mô hình dữ liệu bên dưới.
  moFormNguong = false;
  nguongNhap: number | null = null;
  loiNguong: string | null = null;
  phanTramNhap: number | null = null;
  loiPhanTram: string | null = null;

  constructor(
    private titleService: Title,
    private metaService: Meta,
    private route: ActivatedRoute,
    private gameService: GameService,
    private communityService: CommunityService,
    private newsService: NewsService,
    private alertService: AlertService,
    public authService: AuthService,
    private userService: UserService,
    private structuredData: StructuredDataService,
    @Inject(SITE_ORIGIN) private siteOrigin: string,
    @Optional() @Inject(RENDER_STATUS) private renderStatus: RenderStatus | null,
  ) {}

  ngOnInit(): void {
    const slug = this.route.snapshot.paramMap.get('slug');
    // Bản trước mặc định về 'elden-ring' khi thiếu slug, rồi hiển thị dữ liệu
    // Elden Ring viết cứng cho *mọi* slug. Thiếu slug là URL sai, không phải
    // một game.
    if (!slug) {
      this.markNotFound();
      return;
    }

    this.gameService.getBySlug(slug).subscribe({
      next: (game) => {
        this.game = game;
        this.minimumRows = this.requirementRows(game.system_requirements.minimum);
        this.recommendedRows = this.requirementRows(game.system_requirements.recommended);
        this.isLoading = false;
        this.applySeoTags(game);

        // Fetch related news (if any)
        this.newsService.getNews(5, 0, game.id).subscribe(res => {
          this.relatedNews = res.articles;
        });

        // Fetch community reviews
        this.communityService.getReviews(game.id).subscribe(res => {
          this.reviews = res.reviews;
          this.reviewsTotal = res.total;
        });

        // Đã đặt cảnh báo cho game này chưa (chỉ hỏi khi đã đăng nhập).
        if (this.authService.isLoggedIn()) {
          this.napCanhBao(game.id);
          this.napTheoDoi(game.id);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.isLoading = false;
        if (err.status === 404) {
          this.markNotFound();
          return;
        }
        // Backend chết thì đây là lỗi của ta, không phải URL sai: đừng gắn 404
        // cho nó, nếu không bot sẽ xoá trang có thật khỏi index vì một sự cố
        // tạm thời.
        console.error('Lỗi khi lấy chi tiết game:', err.message);
      },
    });
  }

  /** Giá rẻ nhất — backend đã sort tăng dần trong cùng một region/đồng tiền. */
  get cheapest(): GamePrice | null {
    return this.game?.prices[0] ?? null;
  }

  /** Ngày phát hành sớm nhất. Lấy sớm nhất chứ không lấy region 'ww': nhiều
   *  game Nhật ra ở Nhật trước cả năm. */
  get releaseDate(): string | null {
    const dates = (this.game?.release_dates ?? [])
      .map((rd) => rd.date)
      .filter((date): date is string => !!date)
      .sort();
    return dates[0] ?? null;
  }

  get hasRequirements(): boolean {
    return this.minimumRows.length > 0 || this.recommendedRows.length > 0;
  }

  /** Link tới trang sản phẩm ở store.
   *
   *  Ưu tiên `url` mà nguồn tự trả (job Epic điền sẵn), rồi mới suy ra từ
   *  `steam_appid`. Trước đây chỉ có nhánh Steam, nên khi giá rẻ nhất là một đợt
   *  tặng miễn phí của Epic thì trang không vẽ nút mua nào cả — đúng lúc người
   *  đọc cần bấm nhất. Không có cả hai thì trả null và template không vẽ nút,
   *  thay vì vẽ một nút dẫn đi đâu không biết. */
  storeUrl(price: GamePrice): string | null {
    if (price.url) {
      return price.url;
    }
    if (price.store === 'steam' && this.game?.steam_appid) {
      return `https://store.steampowered.com/app/${this.game.steam_appid}/`;
    }
    return null;
  }

  /** Polyline cho sparkline lịch sử giá, trong hệ toạ độ 100x40 của viewBox.
   *
   *  Quy chiếu về **0**, giống biểu đồ người chơi — bản trước quy chiếu về giá
   *  thấp nhất trong kỳ, và đó là đúng cái sai lệch mà `playerChart` đã tránh.
   *  Đo trên dữ liệu thật: World of Goo giảm 165.000 -> 99.000, tức 40%, nhưng
   *  trục bắt đầu từ min đẩy điểm cuối xuống sát đáy khung (y=40) nên đường vẽ
   *  trông như giảm 100%. Với zero-based, 99.000 nằm ở y=16 — đúng 60% chiều cao
   *  còn lại, khớp tỉ lệ thật.
   *
   *  Dưới 2 điểm thì trả null: một đường thẳng vẽ từ một mốc giá duy nhất trông
   *  y như "giá không đổi suốt 30 ngày", trong khi sự thật là chưa đủ dữ liệu. */
  get sparkline(): string | null {
    const points = this.game?.price_history ?? [];
    if (points.length < 2) {
      return null;
    }
    const values = points.map((p) => p.price_final);
    const max = Math.max(...values);
    return values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * 100;
        // `max === 0` là game free suốt kỳ. Chia cho 0 ra NaN và cả đường biến
        // mất; vẽ sát đáy mới đúng, vì đáy CHÍNH LÀ mốc 0 trong thang này.
        const y = max === 0 ? 40 : 40 - (value / max) * 40;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }

  /** Cột cho biểu đồ số người chơi, trong hệ toạ độ 100x40 của viewBox.
   *
   *  Chiều cao tỉ lệ với `peak` và quy chiếu về **0**, không về giá trị nhỏ
   *  nhất trong kỳ: trục bắt đầu từ min làm một dao động 2% trông như sụp đổ.
   *  Đó là sai lệch kinh điển của biểu đồ cột, và ở đây người đọc đang cố trả
   *  lời "game này còn ai chơi không". */
  get playerChart(): { bars: PlayerBar[]; maxPeak: number } | null {
    const days = this.game?.player_counts ?? [];
    const peaks = days.map((d) => d.peak ?? 0);
    const maxPeak = Math.max(0, ...peaks);
    if (!days.length || maxPeak === 0) {
      return null;
    }
    // Chừa khe giữa các cột, nhưng không để khe rộng hơn cột khi chỉ có 1-2 ngày.
    const slot = 100 / days.length;
    const width = slot * 0.7;
    return {
      maxPeak,
      bars: days.map((day, index) => {
        const height = ((day.peak ?? 0) / maxPeak) * 40;
        return {
          x: index * slot + (slot - width) / 2,
          y: 40 - height,
          width,
          height,
          day,
        };
      }),
    };
  }

  /** Cent USD -> chuỗi đọc được, ví dụ 5159 -> "$51.59".
   *
   *  KHÔNG dùng `toLocaleString('vi-VN')` như các con số VND trên trang: đây là
   *  đô la, và định dạng nó theo quy ước Việt rồi đặt cạnh "₫" là mời người đọc
   *  hiểu sai đơn vị. */
  usd(cents: number | null): string {
    if (cents === null) {
      return '—';
    }
    return `$${(cents / 100).toFixed(2)}`;
  }

  private requirementRows(spec: Record<string, string>): { key: string; value: string }[] {
    return Object.entries(spec).map(([key, value]) => ({ key, value }));
  }

  private markNotFound(): void {
    this.notFound = true;
    this.isLoading = false;
    if (this.renderStatus) {
      this.renderStatus.statusCode = 404;
    }
    this.titleService.setTitle('Không tìm thấy game - GameNews');
    this.metaService.updateTag({ name: 'robots', content: 'noindex' });
    // Điều hướng từ một trang game sang một slug không tồn tại không tải lại
    // trang, nên khối JSON-LD của game trước vẫn còn trong `<head>`: trang 404
    // sẽ khai báo mình là một game có thật, kèm giá.
    this.structuredData.clearJsonLd();
  }

  /**
   * JSON-LD `VideoGame` cho trang game.
   *
   * Chỉ khai những trường ta THẬT SỰ có. Schema.org không bắt buộc trường nào
   * ngoài `name`, và bịa ra `aggregateRating` hay `datePublished` để rich result
   * trông đầy đặn hơn là đúng thứ Google phạt — ngoài chuyện nó nói dối người
   * đọc, vốn là ranh giới của cả dự án này.
   */
  private buildJsonLd(game: GameDetail, url: string): Record<string, unknown> {
    const data: Record<string, unknown> = {
      '@context': 'https://schema.org',
      '@type': 'VideoGame',
      name: game.title,
      url,
    };

    if (game.cover_image_url) {
      data['image'] = game.cover_image_url;
    }
    if (game.platforms.length) {
      data['gamePlatform'] = game.platforms;
    }
    if (game.genres.length) {
      data['genre'] = game.genres;
    }
    if (game.publishers.length) {
      data['publisher'] = game.publishers.map((name) => ({ '@type': 'Organization', name }));
    }
    // `developers` rỗng với mọi game mobile — store chỉ lộ tên tài khoản bán.
    if (game.developers.length) {
      data['author'] = game.developers.map((name) => ({ '@type': 'Organization', name }));
    }
    const released = this.releaseDate;
    if (released) {
      data['datePublished'] = released;
    }

    const price = this.cheapest;
    if (price) {
      const offer: Record<string, unknown> = {
        '@type': 'Offer',
        // Schema.org đòi `price` là số ở dạng chuỗi, không có dấu ngăn nghìn.
        price: String(price.price_final),
        priceCurrency: price.currency,
        availability: game.region_locked_vn
          ? 'https://schema.org/OutOfStock'
          : 'https://schema.org/InStock',
      };
      const storeUrl = this.storeUrl(price);
      if (storeUrl) {
        offer['url'] = storeUrl;
      }
      data['offers'] = offer;
    }

    // Điểm Steam là dữ liệu công khai của Valve và là điểm của CHÍNH game, khác
    // hẳn điểm tổng hợp của Metacritic mà `CLAUDE.md` cấm dùng. Thang 0-100 theo
    // phần trăm review tích cực, khai rõ `bestRating` để không ai đọc nhầm là
    // thang 5 sao.
    const review = game.steam_review;
    if (review && review.total > 0) {
      data['aggregateRating'] = {
        '@type': 'AggregateRating',
        ratingValue: review.positive_percent,
        bestRating: 100,
        worstRating: 0,
        ratingCount: review.total,
      };
    }

    return data;
  }

  private applySeoTags(game: GameDetail): void {
    const price = this.cheapest;
    // Chỉ nhắc giá khi thật sự có giá. Bản trước ghi cứng "595.000₫" vào
    // description của mọi game — mỗi lần ai chia sẻ là một mức giá bịa.
    const priceText = price
      ? ` Giá rẻ nhất ${price.price_final.toLocaleString('vi-VN')}₫ tại ${price.store}.`
      : '';
    const title = `${game.title} - Giá mua, Cấu hình và Thông tin`;
    const description =
      `${game.title}: so sánh giá giữa các store, lịch sử giá và yêu cầu cấu hình.` + priceText;

    this.titleService.setTitle(title);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: title });
    this.metaService.updateTag({ property: 'og:description', content: description });
    this.metaService.updateTag({ property: 'og:type', content: 'product' });

    // URL tuyệt đối, và là origin người ngoài gọi được — xem site-origin.ts.
    if (this.siteOrigin) {
      const pageUrl = `${this.siteOrigin}/game/${game.slug}`;
      this.metaService.updateTag({ property: 'og:url', content: pageUrl });
      this.structuredData.setCanonical(pageUrl);
      this.structuredData.setJsonLd(this.buildJsonLd(game, pageUrl));
      // Hai lần "api" là đúng, đừng rút gọn: `/api` là chỗ proxy của server.ts
      // nhận, còn `/api/v1` là prefix mà `seo_router` của backend tự khai
      // (mọi router khác nằm ở root). Bỏ một lớp là 404, và Facebook sẽ cache
      // lại đúng cái thẻ lỗi đó.
      this.metaService.updateTag({
        property: 'og:image',
        content: `${this.siteOrigin}/api/api/v1/og-image?game=${encodeURIComponent(game.slug)}`,
      });
    }
  }

  /** Đọc lại cảnh báo của game này.
   *
   *  `POST /alerts` là upsert và chỉ trả `{status, game_id, condition}` —
   *  không có `_id`. Nên sau mỗi lần ghi phải đọc lại mới biết id để còn xoá.
   */
  private napCanhBao(gameId: string, xong?: () => void): void {
    this.alertService.getAlerts().subscribe({
      next: (res) => {
        this.canhBaoCuaGame = res.alerts.filter((a) => a.game_id === gameId);
        xong?.();
      },
      // Thiếu nhánh này thì một lượt 401 nổ ra console dưới dạng unhandled còn
      // trang thì vẫn im. Phần còn lại của trang game không phụ thuộc vào
      // cảnh báo, nên nuốt gọn.
      error: () => xong?.(),
    });
  }

  private napTheoDoi(gameId: string, xong?: () => void): void {
    this.userService.getFollows().subscribe({
      next: (res) => {
        this.dangTheoDoi = res.follows.find((f) => f.target_type === 'game' && f.target_id === gameId) ?? null;
        xong?.();
      },
      error: () => xong?.(),
    });
  }

  doiTheoDoi(): void {
    if (!this.game) return;
    const gameId = this.game.id;
    this.dangDoiTheoDoi = true;

    if (this.dangTheoDoi) {
      this.userService.unfollow(this.dangTheoDoi.id).subscribe({
        next: () => this.napTheoDoi(gameId, () => (this.dangDoiTheoDoi = false)),
        error: () => (this.dangDoiTheoDoi = false),
      });
    } else {
      this.userService.follow('game', gameId).subscribe({
        next: () => this.napTheoDoi(gameId, () => (this.dangDoiTheoDoi = false)),
        error: () => (this.dangDoiTheoDoi = false),
      });
    }
  }

  guiReview(): void {
    if (!this.game || this.reviewScore === null) return;
    if (this.reviewScore < 1 || this.reviewScore > 10 || !Number.isInteger(this.reviewScore)) {
      this.loiReview = 'Điểm phải là số nguyên từ 1 đến 10.';
      return;
    }
    this.loiReview = null;
    this.dangGuiReview = true;
    const gameId = this.game.id;

    this.communityService.postReview(gameId, this.reviewScore, this.reviewComment.trim() || null).subscribe({
      next: () => {
        this.dangGuiReview = false;
        this.reviewScore = null;
        this.reviewComment = '';
        // Đọc lại danh sách sau khi lưu xong
        this.communityService.getReviews(gameId).subscribe(res => {
          this.reviews = res.reviews;
          this.reviewsTotal = res.total;
        });
        // Có thể điểm trung bình thay đổi
        this.gameService.getBySlug(this.game!.slug).subscribe(updatedGame => {
            if(this.game) {
                this.game.community_score = updatedGame.community_score;
            }
        });
      },
      error: (err) => {
        this.dangGuiReview = false;
        if (err.status === 422) {
           this.loiReview = 'Dữ liệu không hợp lệ.';
        } else {
           this.loiReview = 'Không thể gửi đánh giá lúc này. Vui lòng thử lại sau.';
        }
      }
    });
  }

  /** Bật/tắt cảnh báo "báo khi chạm đáy lịch sử" cho game đang mở. */
  doiCanhBao(): void {
    if (!this.game) return;
    const gameId = this.game.id;
    const dangCo = this.canhBaoDay;

    this.dangDoiCanhBao = true;

    if (dangCo) {
      this.alertService.deleteAlert(dangCo.id).subscribe({
        next: () => this.napCanhBao(gameId, () => (this.dangDoiCanhBao = false)),
        error: () => (this.dangDoiCanhBao = false),
      });
      return;
    }

    this.alertService.themCanhBao(gameId, 'historical_low').subscribe({
      next: () => this.napCanhBao(gameId, () => (this.dangDoiCanhBao = false)),
      error: () => (this.dangDoiCanhBao = false),
    });
  }

  // --- ngưỡng giá -----------------------------------------------------------

  /** Nhãn nút mở bảng: tóm tắt đúng những gì đang đặt.
   *
   *  Không rút gọn thành "2 cảnh báo" khi có cả hai: con số cụ thể là thứ người
   *  ta quay lại trang này để xem, và nút là chỗ duy nhất thấy được mà không
   *  phải mở bảng ra. */
  get nhanNutNguong(): string {
    const gia = this.canhBaoNguong?.value;
    const pt = this.canhBaoPhanTram?.value;
    const phan: string[] = [];
    if (gia != null) phan.push(`${gia.toLocaleString('vi-VN')}₫`);
    if (pt != null) phan.push(`${pt}%`);
    return phan.length ? `Chờ ${phan.join(' · ')}` : 'Đặt cảnh báo';
  }

  moForm(): void {
    // Đang sửa một cảnh báo có sẵn thì hiện đúng con số cũ, không bắt gõ lại.
    this.nguongNhap = this.canhBaoNguong?.value ?? null;
    this.phanTramNhap = this.canhBaoPhanTram?.value ?? null;
    this.loiNguong = null;
    this.loiPhanTram = null;
    this.moFormNguong = true;
  }

  dongForm(): void {
    this.moFormNguong = false;
    this.loiNguong = null;
    this.loiPhanTram = null;
  }

  /**
   * Ngưỡng đặt **không thấp hơn** giá đang bán.
   *
   * Không phải lỗi, nên đây là lời nhắc chứ không chặn: điều kiện ở backend là
   * `price_final <= value`, mà cảnh báo chỉ được xét khi giá **vừa giảm**. Nên
   * ngưỡng kiểu này sẽ nổ ở đúng lần giảm kế tiếp, bất kể giảm bao nhiêu —
   * người dùng cần biết trước để khỏi tưởng mình vừa đặt một cái bẫy giá rẻ.
   */
  get nguongCaoHonGiaHienTai(): boolean {
    const gia = this.cheapest?.price_final;
    return gia !== undefined && this.nguongNhap !== null && this.nguongNhap >= gia;
  }

  /** Cùng lý lẽ như trên, phía `discount_pct`: điều kiện là
   *  `discount_percent >= value`, nên ngưỡng không cao hơn mức giảm đang chạy
   *  sẽ khớp ngay ở lần giá giảm kế tiếp. */
  get phanTramThapHonMucDangGiam(): boolean {
    const giam = this.cheapest?.discount_percent;
    return giam !== undefined && this.phanTramNhap !== null && this.phanTramNhap <= giam;
  }

  datNguong(): void {
    if (!this.game) return;

    this.loiNguong = kiemNguongGia(this.nguongNhap);
    if (this.loiNguong !== null) return;

    this.ghiCanhBao('below_price', this.nguongNhap as number, (loi) => (this.loiNguong = loi));
  }

  datPhanTram(): void {
    if (!this.game) return;

    this.loiPhanTram = kiemPhanTram(this.phanTramNhap);
    if (this.loiPhanTram !== null) return;

    this.ghiCanhBao('discount_pct', this.phanTramNhap as number, (loi) => (this.loiPhanTram = loi));
  }

  xoaNguong(): void {
    this.xoaCanhBao(this.canhBaoNguong, (loi) => (this.loiNguong = loi));
  }

  xoaPhanTram(): void {
    this.xoaCanhBao(this.canhBaoPhanTram, (loi) => (this.loiPhanTram = loi));
  }

  /** Đặt hoặc cập nhật một cảnh báo. `POST` là upsert nên hai việc là một. */
  private ghiCanhBao(
    condition: 'below_price' | 'discount_pct',
    value: number,
    baoLoi: (loi: string) => void,
  ): void {
    if (!this.game) return;
    const gameId = this.game.id;

    this.dangDoiCanhBao = true;
    this.alertService.themCanhBao(gameId, condition, value).subscribe({
      // Không đóng bảng sau khi lưu: người dùng thường đặt tiếp điều kiện còn
      // lại, và đóng đi thì họ mất luôn chỗ để thấy kết quả vừa lưu.
      next: () => this.napCanhBao(gameId, () => (this.dangDoiCanhBao = false)),
      error: () => {
        this.dangDoiCanhBao = false;
        baoLoi('Không đặt được cảnh báo. Thử lại sau.');
      },
    });
  }

  private xoaCanhBao(alert: PriceAlert | null, baoLoi: (loi: string) => void): void {
    if (!this.game || !alert) return;
    const gameId = this.game.id;

    this.dangDoiCanhBao = true;
    this.alertService.deleteAlert(alert.id).subscribe({
      next: () => this.napCanhBao(gameId, () => (this.dangDoiCanhBao = false)),
      error: () => {
        this.dangDoiCanhBao = false;
        baoLoi('Không xoá được cảnh báo. Thử lại sau.');
      },
    });
  }
}

