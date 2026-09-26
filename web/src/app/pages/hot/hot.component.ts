import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { HotBoard, HotGame, HotService } from '../../services/hot.service';

/** Giá trị `?bang=` đọc được bằng tiếng Việt, map sang tên bảng của API. */
const BANG: Record<string, HotBoard> = { 'pho-bien': 'popular', 'dang-len': 'rising' };

@Component({
  selector: 'app-hot',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './hot.component.html',
})
export class HotComponent implements OnInit, OnDestroy {
  board: HotBoard = 'popular';
  games: HotGame[] = [];
  computedAt: string | null = null;
  isLoading = true;
  loi = false;

  private sub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private hotService: HotService,
    private title: Title,
    private meta: Meta,
  ) {}

  ngOnInit(): void {
    // Bảng nằm trong query chứ không trong state: hai bảng là hai URL chia sẻ
    // được, và SSR render đúng bảng ngay từ lần tải đầu.
    this.sub = this.route.queryParamMap.subscribe((params) => {
      this.board = BANG[params.get('bang') ?? ''] ?? 'popular';
      this.datMeta();
      this.tai();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  private datMeta(): void {
    const dangLen = this.board === 'rising';
    const tieuDe = dangLen
      ? 'Game đang lên - Top game tăng người chơi nhanh nhất - GameNews'
      : 'Game hot nhất - Top game đông người chơi trên Steam - GameNews';
    const moTa = dangLen
      ? 'Những game đang tăng hạng người chơi nhanh nhất trên Steam, kèm giá Steam Việt Nam.'
      : 'Bảng xếp hạng game đông người chơi nhất trên Steam, cập nhật mỗi giờ, kèm giá Steam Việt Nam.';
    this.title.setTitle(tieuDe);
    this.meta.updateTag({ name: 'description', content: moTa });
    this.meta.updateTag({ property: 'og:title', content: tieuDe });
    this.meta.updateTag({ property: 'og:description', content: moTa });
  }

  private tai(): void {
    this.isLoading = true;
    this.loi = false;
    this.hotService.getHot(this.board, 50).subscribe({
      next: (res) => {
        this.games = res.games;
        this.computedAt = res.computed_at;
        this.isLoading = false;
      },
      error: () => {
        this.games = [];
        this.loi = true;
        this.isLoading = false;
      },
    });
  }
}
