import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Meta } from '@angular/platform-browser';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { SearchService, SearchHit, SearchResponse } from '../../services/search.service';

/** Một lựa chọn trong ô lọc: giá trị gửi lên API, và nhãn người dùng đọc. */
interface FilterOption {
  slug: string;
  label: string;
}

/** Thể loại dưới ngưỡng này không lên dropdown.
 *
 * Đo ngày 2026-09-20: `games.genres` có 59 giá trị, 31 trong số đó gắn cho
 * **≤10 game** và 13 giá trị chỉ có **đúng 1 game** (`rts`, `mmorpg`, `crpg`,
 * `accounting`…). Đổ hết vào dropdown thì quá nửa lựa chọn là ngõ cụt — chọn
 * "MMORPG" nhận về một game.
 *
 * Trước đây ngưỡng này được áp **bằng tay** lên một danh sách 19 slug viết
 * cứng, đếm trên Mongo. Nhưng tìm kiếm chạy trên Meilisearch, và ngày
 * 2026-09-26 hai kho lệch nhau 2.939 game: `role-playing`, `board`, `family`,
 * `card` có trong danh sách mà lọc ra 0. Đếm từ chính index mà bộ lọc chạy trên
 * đó thì hai con số không thể lệch nhau.
 */
export const NGUONG_THE_LOAI = 100;

/** Nhãn tiếng Việt. `value` gửi lên API vẫn là slug nguyên văn — backend so
 *  chuỗi, gửi nhãn là 0 kết quả mà không có lỗi nào để lần ra.
 *
 *  Phần lớn là tag Steam nên taxonomy không sạch: `rpg` và `role-playing` là
 *  hai nhánh RỜI NHAU (788/793 game `role-playing` không có `rpg`, đo
 *  2026-09-20) — không gộp được, nên nhãn phải nói rõ để người chọn hiểu vì
 *  sao hai mục giống nhau ra kết quả khác.
 *
 *  Slug vượt ngưỡng mà chưa có ở đây vẫn hiện, bằng `nhanMacDinh()`: thiếu nhãn
 *  đẹp là chuyện nhỏ, mất một thể loại khỏi dropdown mới là chuyện lớn. */
const NHAN_THE_LOAI: Record<string, string> = {
  indie: 'Indie',
  action: 'Hành động',
  adventure: 'Phiêu lưu',
  casual: 'Giải trí nhẹ',
  strategy: 'Chiến thuật',
  simulation: 'Mô phỏng',
  rpg: 'Nhập vai (RPG)',
  'early-access': 'Truy cập sớm',
  'free-to-play': 'Miễn phí chơi',
  sports: 'Thể thao',
  racing: 'Đua xe',
  'massively-multiplayer': 'Nhiều người chơi (MMO)',
  'role-playing': 'Nhập vai (role-playing)',
  violent: 'Bạo lực',
  puzzle: 'Giải đố',
  gore: 'Máu me',
  board: 'Cờ bàn',
  family: 'Gia đình',
  card: 'Thẻ bài',
  education: 'Giáo dục',
  trivia: 'Đố vui',
  word: 'Chữ',
  music: 'Âm nhạc',
  arcade: 'Arcade',
};

function nhanMacDinh(slug: string): string {
  const chu = slug.replace(/-/g, ' ');
  return chu.charAt(0).toUpperCase() + chu.slice(1);
}

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './search.component.html',
  styleUrls: ['./search.component.css']
})
export class SearchComponent implements OnInit, OnDestroy {
  query = '';
  platform = '';
  genre = '';
  year: number | null = null;
  
  page = 1;
  limit = 20;
  
  isLoading = false;
  error = '';
  
  response: SearchResponse | null = null;
  hits: SearchHit[] = [];

  /** `slug` phải khớp nguyên văn giá trị trong `games.platforms` — backend so
   *  chuỗi, không chuẩn hoá. Nhãn thì là tên thương mại, không dịch. */
  readonly PLATFORMS: FilterOption[] = [
    { slug: 'pc', label: 'PC' },
    { slug: 'ps5', label: 'PS5' },
    { slug: 'ps4', label: 'PS4' },
    { slug: 'switch', label: 'Nintendo Switch' },
    { slug: 'xbox-series', label: 'Xbox Series X|S' },
    { slug: 'xbox-one', label: 'Xbox One' },
    { slug: 'android', label: 'Android' },
    { slug: 'ios', label: 'iOS' },
  ];

  /** Thể loại hiện trong dropdown, dựng từ facet của cả catalog — xem
   *  `dungTheLoai()`. Rỗng trong lúc chờ API: ô chỉ còn "Tất cả thể loại",
   *  tìm kiếm vẫn chạy bình thường. */
  theLoai: FilterOption[] = [];

  private soGameTheoTheLoai: Record<string, number> = {};
  private theLoaiSub?: Subscription;

  private sub?: Subscription;
  /** Ô năm gõ từng ký tự nên phải giãn; hai ô select thì đi ngay. */
  private yearInput$ = new Subject<number | null>();
  private yearSub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private searchService: SearchService,
    private meta: Meta,
  ) {}

  ngOnInit(): void {
    // Trang kết quả tìm kiếm nội bộ: vô hạn biến thể theo từ khoá, nội dung
    // trùng trang game. Google khuyên không cho index.
    this.meta.updateTag({ name: 'robots', content: 'noindex' });
    this.theLoaiSub = this.searchService.genreCounts().subscribe({
      next: counts => {
        this.soGameTheoTheLoai = counts;
        this.dungTheLoai();
      },
      // Mất facet không đáng chặn cả trang: dropdown chỉ còn "Tất cả".
      error: err => console.error('Lỗi khi tải danh sách thể loại:', err),
    });

    // `(ngModelChange)` của ô `type="number"` bắn theo từng phím, và mỗi lần
    // `applyFilters()` là một `router.navigate` + một lượt gọi API. Đo được:
    // gõ "2024" sinh **4** lần điều hướng với `year` = 2, 20, 202, 2024; ba
    // giá trị dở dang đều trả 0 kết quả nên người dùng thấy "không tìm thấy"
    // nháy ba lần, và phải bấm Back bốn lần mới rời được trang.
    //
    // 300ms giống `news.component.ts` — cùng bài toán, giữ một con số.
    this.yearSub = this.yearInput$
      .pipe(debounceTime(300), distinctUntilChanged())
      .subscribe(() => this.applyFilters());

    this.sub = this.route.queryParams.subscribe(params => {
      this.query = params['q'] || '';
      this.platform = params['platform'] || '';
      this.genre = params['genre'] || '';
      this.dungTheLoai();
      this.year = params['year'] ? Number(params['year']) : null;
      this.page = Number(params['page']) || 1;
      this.doSearch();
    });
  }

  ngOnDestroy(): void {
    if (this.sub) {
      this.sub.unsubscribe();
    }
    if (this.yearSub) {
      this.yearSub.unsubscribe();
    }
    if (this.theLoaiSub) {
      this.theLoaiSub.unsubscribe();
    }
  }

  /** Thể loại từ `NGUONG_THE_LOAI` game trở lên, nhiều game xếp trước.
   *
   *  Thể loại đang chọn luôn được giữ lại dù dưới ngưỡng: mở link cũ
   *  `?genre=mmorpg` thì ô select vẫn phải hiện đúng thứ đang lọc, không được
   *  trống trơn trong khi kết quả bên dưới đã bị lọc. */
  private dungTheLoai(): void {
    this.theLoai = Object.entries(this.soGameTheoTheLoai)
      .filter(([slug, soGame]) => soGame >= NGUONG_THE_LOAI || slug === this.genre)
      .sort(([, a], [, b]) => b - a)
      .map(([slug]) => ({ slug, label: NHAN_THE_LOAI[slug] ?? nhanMacDinh(slug) }));
  }

  /** Hai ô select: giá trị rời rạc, một lần bấm là một ý định — đi ngay. */
  onFilterChange(): void {
    this.applyFilters();
  }

  /** Ô năm: đẩy qua hàng giãn, đừng gọi thẳng `applyFilters()`. */
  onYearInput(): void {
    this.yearInput$.next(this.year);
  }

  private applyFilters(): void {
    this.router.navigate(['/search'], {
      queryParams: {
        q: this.query || undefined,
        platform: this.platform || undefined,
        genre: this.genre || undefined,
        year: this.year || undefined,
        // Về trang 1: đang ở trang 7 của "indie" rồi lọc sang một thể loại chỉ
        // có 12 kết quả thì trang 7 là rỗng.
        page: 1
      }
    });
  }

  doSearch(): void {
    // Không có từ khoá NHƯNG có bộ lọc thì vẫn tìm: backend cho `q` rỗng, đã
    // đo `q=&genre=rpg` ra 1000 kết quả. Guard chỉ xét `query` khiến chọn thể
    // loại xong nhìn thấy trang trắng.
    if (!this.query.trim() && !this.platform && !this.genre && !this.year) {
      this.hits = [];
      this.response = null;
      return;
    }

    this.isLoading = true;
    this.error = '';

    this.searchService.search(this.query, this.page, this.limit, this.platform || undefined, this.genre || undefined, this.year || undefined).subscribe({
      next: (res) => {
        this.response = res;
        this.hits = res.hits;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Lỗi khi tìm kiếm:', err);
        this.error = 'Không thể tải kết quả tìm kiếm. Vui lòng thử lại sau.';
        this.isLoading = false;
      }
    });
  }
}
