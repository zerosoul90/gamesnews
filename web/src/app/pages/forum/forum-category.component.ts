import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Meta, Title } from '@angular/platform-browser';
import { Subscription, combineLatest } from 'rxjs';

import {
  ChuDeTomTat,
  ChuyenMuc,
  ForumService,
  TrangThaiDang,
  cauBaoLoi,
} from '../../services/forum.service';
import { ForumTrangThaiComponent } from '../../components/forum-trang-thai/forum-trang-thai.component';

/** `/forum/c/:slug?page=N` — chủ đề của một chuyên mục, mới hoạt động xếp trước. */
@Component({
  selector: 'app-forum-category',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ForumTrangThaiComponent],
  templateUrl: './forum-category.component.html',
})
export class ForumCategoryComponent implements OnInit, OnDestroy {
  slug = '';
  chuyenMuc: ChuyenMuc | null = null;
  chuDe: ChuDeTomTat[] = [];
  total = 0;
  page = 1;
  perPage = 20;
  dangTai = true;
  khongCo = false;
  loi: string | null = null;

  trangThai: TrangThaiDang | null = null;
  moForm = false;
  tieuDe = '';
  noiDung = '';
  dangGui = false;
  loiGui: string | null = null;

  private sub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private forum: ForumService,
    private title: Title,
    private meta: Meta,
  ) {}

  ngOnInit(): void {
    this.sub = combineLatest([this.route.paramMap, this.route.queryParamMap]).subscribe(([p, q]) => {
      this.slug = p.get('slug') ?? '';
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

  tai(): void {
    this.dangTai = true;
    this.loi = null;
    this.khongCo = false;

    // Tên chuyên mục chỉ có ở `/categories`; `/threads` chỉ biết slug.
    this.forum.chuyenMuc().subscribe({
      next: (ds) => {
        this.chuyenMuc = ds.find((c) => c.slug === this.slug) ?? null;
        this.datMeta();
      },
    });

    this.forum.danhSach({ category: this.slug }, this.page).subscribe({
      next: (res) => {
        this.chuDe = res.items;
        this.total = res.total;
        this.perPage = res.per_page;
        this.dangTai = false;
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 404) {
          this.khongCo = true;
          this.title.setTitle('Không tìm thấy chuyên mục - GameNews');
          this.meta.updateTag({ name: 'robots', content: 'noindex' });
          return;
        }
        this.loi = 'Không tải được danh sách chủ đề.';
      },
    });
  }

  khiDoiTrangThai(t: TrangThaiDang | null): void {
    this.trangThai = t;
  }

  guiChuDe(): void {
    if (this.dangGui) {
      return;
    }
    this.dangGui = true;
    this.loiGui = null;
    this.forum.taoChuDe({ category: this.slug }, this.tieuDe, this.noiDung).subscribe({
      next: ({ id }) => {
        this.dangGui = false;
        this.router.navigate(['/forum/t', id]);
      },
      error: (err) => {
        this.dangGui = false;
        this.loiGui = cauBaoLoi(err);
      },
    });
  }

  private datMeta(): void {
    if (!this.chuyenMuc) {
      return;
    }
    this.title.setTitle(`${this.chuyenMuc.name} - Diễn đàn GameNews`);
    this.meta.updateTag({ name: 'description', content: this.chuyenMuc.description });
  }
}
