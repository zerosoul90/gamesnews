import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';
import { SearchService, SearchHit, SearchResponse } from '../../services/search.service';

/** Một lựa chọn trong ô lọc: giá trị gửi lên API, và nhãn người dùng đọc. */
interface FilterOption {
  slug: string;
  label: string;
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

  /** Thể loại có **từ 100 game trở lên**, xếp theo số game giảm dần.
   *
   * Vì sao cắt ngưỡng: `games.genres` có 59 giá trị, nhưng 31 trong số đó gắn
   * cho **≤10 game** và 13 giá trị chỉ có **đúng 1 game** (`rts`, `mmorpg`,
   * `battle-royale`, `crpg`, `accounting`…). Đổ cả 59 vào một dropdown thì quá
   * nửa lựa chọn là ngõ cụt — người dùng chọn "MMORPG" và nhận về một game.
   * Danh sách này là 19 giá trị còn lại, đo ngày 2026-09-20 trên 39.284 game.
   *
   * Phần lớn là tag của Steam nên taxonomy không sạch: `rpg` (6.734) và
   * `role-playing` (793) là hai nhánh RỜI NHAU — 788/793 game mang
   * `role-playing` không hề có `rpg` — nên không gộp được, và nhãn phải nói rõ
   * để người chọn hiểu vì sao hai mục nghe giống nhau lại ra kết quả khác.
   *
   * Cập nhật bằng tay khi catalog đổi đáng kể. Không có endpoint facet nào để
   * dựng động; thêm một cái là việc backend.
   */
  readonly GENRES: FilterOption[] = [
    { slug: 'indie', label: 'Indie' },
    { slug: 'action', label: 'Hành động' },
    { slug: 'adventure', label: 'Phiêu lưu' },
    { slug: 'casual', label: 'Giải trí nhẹ' },
    { slug: 'strategy', label: 'Chiến thuật' },
    { slug: 'simulation', label: 'Mô phỏng' },
    { slug: 'rpg', label: 'Nhập vai (RPG)' },
    { slug: 'early-access', label: 'Truy cập sớm' },
    { slug: 'free-to-play', label: 'Miễn phí chơi' },
    { slug: 'sports', label: 'Thể thao' },
    { slug: 'racing', label: 'Đua xe' },
    { slug: 'massively-multiplayer', label: 'Nhiều người chơi (MMO)' },
    { slug: 'role-playing', label: 'Nhập vai (role-playing)' },
    { slug: 'violent', label: 'Bạo lực' },
    { slug: 'puzzle', label: 'Giải đố' },
    { slug: 'gore', label: 'Máu me' },
    { slug: 'board', label: 'Cờ bàn' },
    { slug: 'family', label: 'Gia đình' },
    { slug: 'card', label: 'Thẻ bài' },
  ];

  private sub?: Subscription;
  /** Ô năm gõ từng ký tự nên phải giãn; hai ô select thì đi ngay. */
  private yearInput$ = new Subject<number | null>();
  private yearSub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private searchService: SearchService
  ) {}

  ngOnInit(): void {
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
