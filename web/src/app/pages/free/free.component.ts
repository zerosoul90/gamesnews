import { Component, OnInit } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { DealService, FreeGame } from '../../services/deal.service';

/**
 * Trang game miễn phí tuần này.
 *
 * Bản trước của trang này là một **mockup tĩnh**: component không có
 * `HttpClient`, `imports: []`, và template không có lấy một binding nào. Nó khoe
 * cứng "Marvel's Midnight Suns — 1.000.000₫ — Còn 3 ngày" với một URL ảnh Epic
 * CDN đã chết, trong khi API thật trả về LUFTRAUSERS.
 *
 * Tức nó không chỉ thiếu tính năng mà còn **nói sai** — tệ hơn hẳn một trang
 * trống, vì trang trống thì người dùng biết là chưa có gì.
 */
@Component({
  selector: 'app-free',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './free.component.html',
  styleUrl: './free.component.css',
})
export class FreeComponent implements OnInit {
  freeGames: FreeGame[] = [];
  isLoading = true;
  coLoi = false;

  constructor(
    private titleService: Title,
    private metaService: Meta,
    private dealService: DealService,
  ) {}

  ngOnInit(): void {
    const pageTitle = 'Game Miễn Phí Tuần Này - Nhận ngay kẻo lỡ!';
    const description =
      'Tổng hợp danh sách các tựa game đang được phát hành miễn phí 100% trên Epic Games, Steam. Thêm vào thư viện ngay, chơi lúc nào tùy thích.';

    this.titleService.setTitle(pageTitle);
    this.metaService.updateTag({ name: 'description', content: description });
    this.metaService.updateTag({ property: 'og:title', content: pageTitle });
    this.metaService.updateTag({ property: 'og:description', content: description });

    this.tai();
  }

  tai(): void {
    this.isLoading = true;
    this.coLoi = false;
    this.dealService.getFreeGames().subscribe({
      next: (res) => {
        this.freeGames = res.free_games || [];
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Lỗi khi lấy game miễn phí:', err);
        this.coLoi = true;
        this.isLoading = false;
      },
    });
  }

  /**
   * Số ngày còn lại của đợt tặng.
   *
   * `null` khi store không công bố mốc kết thúc — trả `null` chứ không đoán một
   * con số, vì "Còn 3 ngày" cứng là đúng cái sai mà bản mockup mắc phải.
   *
   * Làm tròn LÊN, nên phần lẻ của ngày cuối vẫn được tính là một ngày: đợt còn
   * 4 tiếng hiện "còn 1 ngày" chứ không phải "còn 0 ngày".
   *
   * Trả 0 khi đợt đã hết hạn, và template coi 0 là không hiện huy hiệu — một
   * cái đếm ngược đã âm thì không nói thêm được gì.
   */
  soNgayConLai(promoEndsAt: string | null): number | null {
    if (!promoEndsAt) {
      return null;
    }
    const ket = new Date(promoEndsAt).getTime();
    if (Number.isNaN(ket)) {
      return null;
    }
    const conLai = ket - Date.now();
    if (conLai <= 0) {
      return 0;
    }
    return Math.ceil(conLai / (1000 * 60 * 60 * 24));
  }
}
