import { Component, Inject, OnDestroy, OnInit, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Meta, Title } from '@angular/platform-browser';
import { Subscription, combineLatest } from 'rxjs';

import { AuthService } from '../../services/auth.service';
import {
  BaiTraLoi,
  ChuDeChiTiet,
  ForumService,
  TrangThaiDang,
  cauBaoLoi,
} from '../../services/forum.service';
import { ForumTrangThaiComponent } from '../../components/forum-trang-thai/forum-trang-thai.component';

/** Lý do báo cáo cho người dùng chọn. Backend nhận chuỗi tự do ≤500 ký tự;
 *  cho chọn sẵn để admin gom nhóm được ở chặng F3. */
export const LY_DO_BAO_CAO = ['Spam / quảng cáo', 'Xúc phạm, công kích', 'Nội dung phản cảm', 'Lừa đảo'];

/** Ô đang mở báo cáo: chủ đề, hoặc một bài trả lời cụ thể. */
interface DangBaoCao {
  loai: 'thread' | 'post';
  id: string;
}

/** Bài đang sửa tại chỗ. `tieuDe` chỉ dùng khi sửa chủ đề. */
interface DangSua {
  loai: 'thread' | 'post';
  id: string;
  tieuDe: string;
  noiDung: string;
}

/**
 * `/forum/t/:id?page=N` — một chủ đề và các trả lời.
 *
 * Mọi nội dung người dùng đi qua nội suy `{{ }}` (Angular tự escape) với
 * `whitespace-pre-line` để giữ xuống dòng. **Không bao giờ `[innerHTML]`** —
 * backend lưu text thuần và không lọc HTML, nên đây là lớp duy nhất đứng giữa
 * một bài viết chứa `<script>` và trình duyệt của người đọc.
 */
@Component({
  selector: 'app-forum-thread',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ForumTrangThaiComponent],
  templateUrl: './forum-thread.component.html',
})
export class ForumThreadComponent implements OnInit, OnDestroy {
  readonly lyDoBaoCao = LY_DO_BAO_CAO;

  id = '';
  chuDe: ChuDeChiTiet | null = null;
  /** Tên hiển thị của chuyên mục; `chuDe.category` chỉ là slug. */
  tenChuyenMuc: string | null = null;
  baiTraLoi: BaiTraLoi[] = [];
  tongTraLoi = 0;
  page = 1;
  perPage = 30;
  dangTai = true;
  khongCo = false;
  loi: string | null = null;

  trangThai: TrangThaiDang | null = null;
  noiDung = '';
  trichBai: BaiTraLoi | null = null;
  dangGui = false;
  loiGui: string | null = null;

  dangBaoCao: DangBaoCao | null = null;
  dangSua: DangSua | null = null;
  loiSua: string | null = null;
  lyDoChon = LY_DO_BAO_CAO[0];
  thongBao: string | null = null;

  private sub?: Subscription;
  private readonly laTrinhDuyet: boolean;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private forum: ForumService,
    private auth: AuthService,
    private title: Title,
    private meta: Meta,
    @Inject(PLATFORM_ID) platformId: object,
  ) {
    this.laTrinhDuyet = isPlatformBrowser(platformId);
  }

  ngOnInit(): void {
    this.sub = combineLatest([this.route.paramMap, this.route.queryParamMap]).subscribe(([p, q]) => {
      this.id = p.get('id') ?? '';
      this.page = Math.max(1, Number(q.get('page')) || 1);
      this.tai();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  get conTrangSau(): boolean {
    return this.page * this.perPage < this.tongTraLoi;
  }

  get duocTraLoi(): boolean {
    return (
      !!this.trangThai?.can_post && !!this.chuDe && !this.chuDe.locked && this.chuDe.status === 'visible'
    );
  }

  /** Bài của chính người đang xem — chỉ để hiện nút xoá. Quyền thật vẫn do
   *  backend kiểm (403 với bài người khác); đây chỉ là che nút cho đỡ rối. */
  cuaToi(authorId: string): boolean {
    return this.auth.currentUserValue?.user_id === authorId;
  }

  tai(): void {
    this.dangTai = true;
    this.loi = null;
    this.khongCo = false;
    this.forum.chuDe(this.id, this.page).subscribe({
      next: (res) => {
        this.chuDe = res.thread;
        this.baiTraLoi = res.posts;
        this.tongTraLoi = res.total_posts;
        this.perPage = res.per_page;
        this.dangTai = false;
        this.datMeta(res.thread);
        this.taiTenChuyenMuc(res.thread.category);
      },
      error: (err) => {
        this.dangTai = false;
        if (err.status === 404) {
          // Bị ẩn, bị xoá, hay id sai đều là 404 — backend cố ý không phân biệt.
          this.khongCo = true;
          this.title.setTitle('Không tìm thấy chủ đề - GameNews');
          this.meta.updateTag({ name: 'robots', content: 'noindex' });
          return;
        }
        this.loi = 'Không tải được chủ đề.';
      },
    });
  }

  khiDoiTrangThai(t: TrangThaiDang | null): void {
    this.trangThai = t;
  }

  trich(bai: BaiTraLoi): void {
    this.trichBai = bai;
    if (this.laTrinhDuyet) {
      document.getElementById('tra-loi')?.focus();
    }
  }

  guiTraLoi(): void {
    if (this.dangGui || !this.chuDe) {
      return;
    }
    this.dangGui = true;
    this.loiGui = null;
    this.forum.traLoi(this.chuDe.id, this.noiDung, this.trichBai?.id ?? null).subscribe({
      next: () => {
        this.dangGui = false;
        this.noiDung = '';
        this.trichBai = null;
        // Bài mới nằm ở trang cuối; tổng sau khi thêm là `tongTraLoi + 1`.
        const trangCuoi = Math.max(1, Math.ceil((this.tongTraLoi + 1) / this.perPage));
        if (trangCuoi === this.page) {
          this.tai();
        } else {
          this.router.navigate(['/forum/t', this.chuDe!.id], { queryParams: { page: trangCuoi } });
        }
      },
      error: (err) => {
        this.dangGui = false;
        this.loiGui = cauBaoLoi(err);
      },
    });
  }

  moBaoCao(loai: 'thread' | 'post', id: string): void {
    this.dangBaoCao = { loai, id };
    this.lyDoChon = LY_DO_BAO_CAO[0];
    this.thongBao = null;
  }

  guiBaoCao(): void {
    const bc = this.dangBaoCao;
    if (!bc) {
      return;
    }
    this.forum.baoCao(bc.loai, bc.id, this.lyDoChon).subscribe({
      next: ({ hidden }) => {
        this.dangBaoCao = null;
        this.thongBao = hidden
          ? 'Đã nhận báo cáo. Bài đã bị ẩn chờ ban quản trị xem xét.'
          : 'Đã nhận báo cáo, cảm ơn bạn.';
        if (hidden) {
          this.tai();
        }
      },
      error: (err) => {
        this.dangBaoCao = null;
        this.thongBao = cauBaoLoi(err);
      },
    });
  }

  xoaChuDe(): void {
    if (!this.chuDe || !this.xacNhan('Xoá chủ đề này? Các trả lời cũng sẽ không còn hiển thị.')) {
      return;
    }
    this.forum.xoaChuDe(this.chuDe.id).subscribe({
      next: () => this.router.navigate(['/forum']),
      error: (err) => (this.thongBao = cauBaoLoi(err)),
    });
  }

  xoaTraLoi(bai: BaiTraLoi): void {
    if (!this.xacNhan('Xoá bài trả lời này?')) {
      return;
    }
    this.forum.xoaTraLoi(bai.id).subscribe({
      next: () => this.tai(),
      error: (err) => (this.thongBao = cauBaoLoi(err)),
    });
  }

  private taiTenChuyenMuc(slug: string | null): void {
    if (!slug || this.tenChuyenMuc) {
      return;
    }
    this.forum.chuyenMuc().subscribe({
      next: (ds) => (this.tenChuyenMuc = ds.find((c) => c.slug === slug)?.name ?? null),
    });
  }

  moSuaChuDe(): void {
    if (!this.chuDe) {
      return;
    }
    this.dangSua = { loai: 'thread', id: this.chuDe.id, tieuDe: this.chuDe.title, noiDung: this.chuDe.body };
    this.loiSua = null;
  }

  moSuaTraLoi(bai: BaiTraLoi): void {
    this.dangSua = { loai: 'post', id: bai.id, tieuDe: '', noiDung: bai.body };
    this.loiSua = null;
  }

  luuSua(): void {
    const sua = this.dangSua;
    if (!sua) {
      return;
    }
    const goi =
      sua.loai === 'thread'
        ? this.forum.suaChuDe(sua.id, { title: sua.tieuDe, body: sua.noiDung })
        : this.forum.suaTraLoi(sua.id, sua.noiDung);
    goi.subscribe({
      next: () => {
        this.dangSua = null;
        this.tai();
      },
      error: (err) => (this.loiSua = cauBaoLoi(err)),
    });
  }

  private xacNhan(cau: string): boolean {
    return this.laTrinhDuyet && window.confirm(cau);
  }

  private datMeta(t: ChuDeChiTiet): void {
    this.title.setTitle(`${t.title} - Diễn đàn GameNews`);
    // Mô tả lấy từ nội dung bài: đoạn đầu, gộp dòng, cắt ở 160 ký tự.
    const moTa = t.body.replace(/\s+/g, ' ').trim().slice(0, 160);
    this.meta.updateTag({ name: 'description', content: moTa });
    this.meta.updateTag({ property: 'og:title', content: t.title });
    this.meta.updateTag({ property: 'og:description', content: moTa });
  }
}
