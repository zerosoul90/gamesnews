import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Meta, Title } from '@angular/platform-browser';
import { Subscription } from 'rxjs';

import { ChuDeTomTat, ForumService, cauBaoLoi } from '../../services/forum.service';

/**
 * `/forum/tim-kiem?q=...&page=N` — tìm chủ đề theo tiêu đề và nội dung.
 *
 * Từ khoá nằm trong URL để kết quả chia sẻ được và Back hoạt động. Không tìm
 * theo từng phím: chỉ khi bấm tìm (Enter), vì mỗi lần là một truy vấn text
 * index — cùng bài học với ô năm ở trang tìm game.
 *
 * `noindex`: trang kết quả tìm kiếm nội bộ là nội dung mỏng, trùng lặp vô hạn
 * theo từ khoá — Google khuyên không cho index.
 */
@Component({
  selector: 'app-forum-search',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './forum-search.component.html',
})
export class ForumSearchComponent implements OnInit, OnDestroy {
  q = '';
  tuKhoa = '';
  page = 1;
  perPage = 20;
  ketQua: ChuDeTomTat[] = [];
  total = 0;
  dangTai = false;
  loi: string | null = null;

  private sub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private forum: ForumService,
    private title: Title,
    private meta: Meta,
  ) {}

  ngOnInit(): void {
    this.title.setTitle('Tìm trong diễn đàn - GameNews');
    this.meta.updateTag({ name: 'robots', content: 'noindex' });
    this.sub = this.route.queryParamMap.subscribe((q) => {
      this.q = (q.get('q') ?? '').trim();
      this.tuKhoa = this.q;
      this.page = Math.max(1, Number(q.get('page')) || 1);
      this.tai();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  get conTrangSau(): boolean {
    return this.page * this.perPage < this.total;
  }

  tim(): void {
    const q = this.tuKhoa.trim();
    if (!q) {
      return;
    }
    this.router.navigate(['/forum/tim-kiem'], { queryParams: { q } });
  }

  private tai(): void {
    this.ketQua = [];
    this.total = 0;
    this.loi = null;
    if (!this.q) {
      return;
    }
    this.dangTai = true;
    this.forum.timKiem(this.q, this.page).subscribe({
      next: (res) => {
        this.ketQua = res.items;
        this.total = res.total;
        this.perPage = res.per_page;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        this.loi = cauBaoLoi(err, 'Không tìm được, thử lại sau.');
      },
    });
  }
}
