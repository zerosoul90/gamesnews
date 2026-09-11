import { InjectionToken } from '@angular/core';

/** Hộp chứa status code để component nói ngược lại cho Express. */
export interface RenderStatus {
  statusCode: number;
}

/**
 * `CommonEngine.render()` chỉ trả về HTML, không nói route nào đã khớp — nên tự
 * nó Express không thể biết nên đáp 200 hay 404. Mỗi request được cấp một object
 * `RenderStatus` riêng; component nào cần đổi status thì ghi vào đó trong lúc
 * render, và `server.ts` đọc lại sau khi render xong.
 *
 * Chỉ phía server cung cấp token này, nên chỗ inject phải `@Optional()`: cùng
 * component đó còn chạy trên browser, nơi không có status code nào để đặt.
 */
export const RENDER_STATUS = new InjectionToken<RenderStatus>('RENDER_STATUS');
