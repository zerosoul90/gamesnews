import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Article, NewsService } from '../../services/news.service';
import { SearchService, SearchHit } from '../../services/search.service';
import { FormsModule } from '@angular/forms';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

/**
 * Trang tin.
 *
 * Đây là chỗ ra đầu tiên của cả đường ống Phase 6: crawl 15 nguồn RSS, khử trùng
 * simhash, gắn entity ba tầng, rồi dịch qua Gemini dưới trần hạn mức ngày. Trước
 * trang này toàn bộ kết quả nằm trong Mongo mà không ai đọc được.
 */
@Component({
  selector: 'app-news',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './news.component.html',
})
export class NewsComponent implements OnInit {
  articles: Article[] = [];
  total = 0;
  isLoading = true;
  /** Khác `isLoading`: lần tải đầu thay cả trang bằng chữ "đang tải", còn lần
   *  bấm "xem thêm" phải GIỮ danh sách cũ trên màn hình. Dùng chung một cờ thì
   *  trang chớp trắng mỗi lần tải thêm. */
  dangTaiThem = false;
  coLoi = false;

  private readonly soMoiTrang = 20;

  // Game filter
  selectedGameId: string | null = null;
  selectedGameTitle: string | null = null;
  searchQuery = '';
  searchResults: SearchHit[] = [];
  dangTimKiem = false;
  hienDropdown = false;
  private searchSubject = new Subject<string>();

  constructor(
    private titleService: Title,
    private metaService: Meta,
    private newsService: NewsService,
    private searchService: SearchService,
  ) {}

  ngOnInit(): void {
    const pageTitle = 'Tin Game Mới Nhất - Tóm tắt tiếng Việt';
    const description =
      'Tin tức game quốc tế được tóm tắt sang tiếng Việt, cập nhật liên tục từ các nguồn lớn như IGN, PC Gamer, Destructoid.';

    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });

    this.searchSubject.pipe(
      debounceTime(300),
      distinctUntilChanged()
    ).subscribe(query => {
      this.thucHienTimKiem(query);
    });

    this.tai();
  }

  onSearchChange(): void {
    this.hienDropdown = true;
    this.searchSubject.next(this.searchQuery);
  }

  private thucHienTimKiem(query: string): void {
    if (!query.trim()) {
      this.searchResults = [];
      this.dangTimKiem = false;
      return;
    }
    this.dangTimKiem = true;
    this.searchService.search(query, 1, 5).subscribe({
      next: (res) => {
        this.searchResults = res.hits;
        this.dangTimKiem = false;
      },
      error: () => {
        this.dangTimKiem = false;
        this.searchResults = [];
      }
    });
  }

  chonGame(hit: SearchHit): void {
    this.selectedGameId = hit.id;
    this.selectedGameTitle = hit.titles.primary || hit.titles.vi || hit.slug;
    this.searchQuery = '';
    this.hienDropdown = false;
    // Reset and fetch
    this.articles = [];
    this.tai();
  }

  xoaLoc(): void {
    this.selectedGameId = null;
    this.selectedGameTitle = null;
    this.searchQuery = '';
    this.articles = [];
    this.tai();
  }

  /** Còn bài chưa tải hay không. So với `total` của API chứ không so độ dài
   *  trang với `limit`: cách sau sai đúng ở ca trang cuối vừa tròn. */
  get conNua(): boolean {
    return this.articles.length < this.total;
  }

  tai(): void {
    const themVao = this.articles.length > 0;
    if (themVao) {
      this.dangTaiThem = true;
    } else {
      this.isLoading = true;
    }
    this.coLoi = false;

    this.newsService.getNews(this.soMoiTrang, this.articles.length, this.selectedGameId || undefined).subscribe({
      next: (res) => {
        this.articles = [...this.articles, ...(res.articles || [])];
        this.total = res.total ?? 0;
        this.isLoading = false;
        this.dangTaiThem = false;
      },
      error: (err) => {
        console.error('Lỗi khi lấy tin:', err);
        this.coLoi = true;
        this.isLoading = false;
        this.dangTaiThem = false;
      },
    });
  }
}
