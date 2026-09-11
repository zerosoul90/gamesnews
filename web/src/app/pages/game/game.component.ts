import { Component, Inject, OnInit, Optional } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { RENDER_STATUS, RenderStatus } from '../../render-status';
import { SITE_ORIGIN } from '../../site-origin';
import { GameDetail, GamePrice, GameService, PlayerCountDay } from '../../services/game.service';

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
  imports: [CommonModule, RouterLink],
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

  constructor(
    private titleService: Title,
    private metaService: Meta,
    private route: ActivatedRoute,
    private gameService: GameService,
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
   *  Dưới 2 điểm thì trả null: một đường thẳng vẽ từ một mốc giá duy nhất trông
   *  y như "giá không đổi suốt 30 ngày", trong khi sự thật là chưa đủ dữ liệu.
   *  Giá không đổi trong kỳ cũng cho `span = 0` — chia cho nó ra NaN và đường
   *  biến mất, nên trường hợp đó vẽ thẳng ở giữa. */
  get sparkline(): string | null {
    const points = this.game?.price_history ?? [];
    if (points.length < 2) {
      return null;
    }
    const values = points.map((p) => p.price_final);
    const min = Math.min(...values);
    const span = Math.max(...values) - min;
    return values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * 100;
        const y = span === 0 ? 20 : 40 - ((value - min) / span) * 40;
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
      this.metaService.updateTag({
        property: 'og:url',
        content: `${this.siteOrigin}/game/${game.slug}`,
      });
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
}
