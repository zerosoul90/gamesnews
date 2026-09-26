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
  GameRef,
  NoiDang,
  TrangThaiDang,
  cauBaoLoi,
} from '../../services/forum.service';
import { ForumTrangThaiComponent } from '../../components/forum-trang-thai/forum-trang-thai.component';

/**
 * Danh sách chủ đề, mới hoạt động xếp trước. Hai chế độ, một component:
 *
 * - `/forum/c/:slug` — chuyên mục chung;
 * - `/forum/g/:gameSlug` — khu thảo luận của một game.
 *
 * Tách hai trang thì danh sách, phân trang, form tạo chủ đề bị chép đôi, và
 * lần sửa sau sẽ chỉ sửa một bản.
 */
@Component({
  selector: 'app-forum-category',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ForumTrangThaiComponent],
  templateUrl: './forum-category.component.html',
})
export class ForumCategoryComponent implements OnInit, OnDestroy {
  slug = '';
  gameSlug = '';
  chuyenMuc: ChuyenMuc | null = null;
  game: GameRef | null = null;
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
      this.gameSlug = p.get('gameSlug') ?? '';
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

  get laGame(): boolean {
    return this.gameSlug !== '';
  }

  get tenTrang(): string {
    return (this.laGame ? this.game?.title : this.chuyenMuc?.name) || this.slug || this.gameSlug;
  }

  /** Gốc của link phân trang — giữ đúng chế độ đang xem. */
  get duongDanGoc(): string[] {
    return this.laGame ? ['/forum/g', this.gameSlug] : ['/forum/c', this.slug];
  }

  /** Nơi ĐỌC: game thì lọc thẳng theo slug trong URL — `/threads` trả kèm id
   *  và tên game, khỏi gọi `/games/by-slug` (kéo cả giá + lịch sử giá). */
  private get noiDoc(): NoiDang {
    return this.laGame ? { game_slug: this.gameSlug } : { category: this.slug };
  }

  /** Nơi GHI: backend nhận `game_id`, nên phải đợi lượt đọc đầu trả id về. */
  private get noiGhi(): NoiDang | null {
    if (!this.laGame) {
      return { category: this.slug };
    }
    return this.game ? { game_id: this.game.id } : null;
  }

  tai(): void {
    this.dangTai = true;
    this.loi = null;
    this.khongCo = false;

    if (this.laGame) {
      this.taiChuDe();
      return;
    }

    // Tên chuyên mục chỉ có ở `/categories`; `/threads` chỉ biết slug.
    this.forum.chuyenMuc().subscribe({
      next: (ds) => {
        this.chuyenMuc = ds.find((c) => c.slug === this.slug) ?? null;
        this.datMeta();
      },
    });
    this.taiChuDe();
  }

  private taiChuDe(): void {
    this.forum.danhSach(this.noiDoc, this.page).subscribe({
      next: (res) => {
        if (res.game) {
          this.game = res.game;
          this.datMeta();
        }
        this.chuDe = res.items;
        this.total = res.total;
        this.perPage = res.per_page;
        this.dangTai = false;
      },
      error: (err) => this.baoLoi(err),
    });
  }

  private baoLoi(err: { status?: number }): void {
    this.dangTai = false;
    if (err.status === 404) {
      this.khongCo = true;
      this.title.setTitle('Không tìm thấy - GameNews');
      this.meta.updateTag({ name: 'robots', content: 'noindex' });
      return;
    }
    this.loi = 'Không tải được danh sách chủ đề.';
  }

  khiDoiTrangThai(t: TrangThaiDang | null): void {
    this.trangThai = t;
  }

  guiChuDe(): void {
    const noi = this.noiGhi;
    if (this.dangGui || !noi) {
      return;
    }
    this.dangGui = true;
    this.loiGui = null;
    this.forum.taoChuDe(noi, this.tieuDe, this.noiDung).subscribe({
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
    if (this.laGame && this.game) {
      this.title.setTitle(`Thảo luận ${this.game.title} - Diễn đàn GameNews`);
      this.meta.updateTag({
        name: 'description',
        content: `Người chơi trao đổi về ${this.game.title}: hỏi đáp, kinh nghiệm, tìm đồng đội.`,
      });
    } else if (this.chuyenMuc) {
      this.title.setTitle(`${this.chuyenMuc.name} - Diễn đàn GameNews`);
      this.meta.updateTag({ name: 'description', content: this.chuyenMuc.description });
    }
  }
}
