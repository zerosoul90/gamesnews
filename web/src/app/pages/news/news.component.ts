import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Article, NewsService } from '../../services/news.service';

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
  imports: [CommonModule, RouterLink],
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

  constructor(
    private titleService: Title,
    private metaService: Meta,
    private newsService: NewsService,
  ) {}

  ngOnInit(): void {
    const pageTitle = 'Tin Game Mới Nhất - Tóm tắt tiếng Việt';
    const description =
      'Tin tức game quốc tế được tóm tắt sang tiếng Việt, cập nhật liên tục từ các nguồn lớn như IGN, PC Gamer, Destructoid.';

    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });

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

    this.newsService.getNews(this.soMoiTrang, this.articles.length).subscribe({
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
