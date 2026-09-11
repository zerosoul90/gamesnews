import { DOCUMENT } from '@angular/common';
import { Inject, Injectable } from '@angular/core';

/**
 * Structured data (JSON-LD) và thẻ canonical — `docs/PHASE-4.md` mục 5.
 *
 * Vì sao cần một service riêng thay vì nhét thẳng vào template: JSON-LD phải
 * nằm trong `<head>` dưới dạng một `<script type="application/ld+json">` với
 * nội dung là JSON hợp lệ. Đặt nó trong template Angular thì mọi dấu ngoặc kép
 * bị escape thành `&quot;` và Google đọc ra một khối JSON hỏng — mà nó không
 * báo lỗi gì, chỉ lặng lẽ bỏ qua rich result.
 *
 * Ghi vào DOM lúc `ngOnInit` nên chạy cả ở SSR: `CommonEngine` serialise
 * document sau khi component đã khởi tạo, nên thẻ có mặt trong HTML thô mà bot
 * nhận được — đó là toàn bộ mục đích, vì Googlebot không phải lúc nào cũng chạy
 * JavaScript.
 *
 * Mỗi loại dùng một `id` cố định và **ghi đè** thay vì thêm mới: điều hướng
 * trong app không tải lại trang, nên nếu cứ append thì sang trang game thứ ba
 * trong `<head>` có ba khối JSON-LD mô tả ba game khác nhau.
 */
@Injectable({ providedIn: 'root' })
export class StructuredDataService {
  private static readonly LD_ID = 'ld-json-primary';
  private static readonly CANONICAL_ID = 'canonical-link';

  constructor(@Inject(DOCUMENT) private document: Document) {}

  /** Đặt (hoặc thay) khối JSON-LD của trang hiện tại. */
  setJsonLd(data: Record<string, unknown>): void {
    const head = this.document.head;
    if (!head) {
      return;
    }

    let script = this.document.getElementById(
      StructuredDataService.LD_ID,
    ) as HTMLScriptElement | null;

    if (!script) {
      script = this.document.createElement('script');
      script.id = StructuredDataService.LD_ID;
      script.type = 'application/ld+json';
      head.appendChild(script);
    }

    script.textContent = JSON.stringify(data);
  }

  /**
   * Đặt (hoặc thay) `<link rel="canonical">`.
   *
   * `og:url` KHÔNG thay được thẻ này: Facebook đọc `og:url`, còn Google đọc
   * `rel=canonical`. Thiếu nó thì mỗi biến thể URL (`?utm_source=...`, dấu `/`
   * cuối) là một trang riêng trong mắt Google, và điểm của một trang bị chia ra
   * cho các bản sao của chính nó.
   */
  setCanonical(url: string): void {
    const head = this.document.head;
    if (!head || !url) {
      return;
    }

    let link = this.document.getElementById(
      StructuredDataService.CANONICAL_ID,
    ) as HTMLLinkElement | null;

    if (!link) {
      link = this.document.createElement('link');
      link.id = StructuredDataService.CANONICAL_ID;
      link.rel = 'canonical';
      head.appendChild(link);
    }

    link.href = url;
  }

  /** Gỡ JSON-LD. Trang 404 không được mang schema của game trước đó. */
  clearJsonLd(): void {
    this.document.getElementById(StructuredDataService.LD_ID)?.remove();
  }
}
