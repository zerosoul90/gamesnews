import { routes } from './app.routes';

/**
 * Cấu hình route — hai bất biến dễ vỡ lặng lẽ khi thêm trang mới.
 */
describe('app.routes', () => {
  it('chỉ ba trang nạp ngay; mọi trang khác lazy', () => {
    // Trước lượt dọn nợ, cả 14 trang nạp ngay: bundle ban đầu 541 kB, vượt
    // ngưỡng cảnh báo 500 kB. Thêm một trang bằng `component:` là kéo nó vào
    // bundle của mọi khách — test này bắt lúc đó.
    const napNgay = routes.filter((r) => r.component).map((r) => r.path);
    expect(napNgay.sort()).toEqual(['', '**', 'deals'].sort());
  });

  it('trang không tự đặt tiêu đề phải có `title` ở route', () => {
    // Bốn trang này từng hiện "Web" (tiêu đề mặc định của index.html) trên tab
    // trình duyệt và kết quả Google.
    const tieuDe = new Map(routes.map((r) => [r.path, r.title]));
    for (const path of ['login', 'profile', 'search', 'thong-ke']) {
      expect(tieuDe.get(path)).withContext(path).toMatch(/GameNews$/);
    }
  });
});
