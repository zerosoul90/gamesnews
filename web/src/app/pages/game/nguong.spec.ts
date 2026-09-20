import { kiemNguongGia, kiemPhanTram } from './nguong';

/**
 * Biên của ô nhập ngưỡng.
 *
 * Đáng chốt vì ba lý do, và cả ba đều im lặng khi hỏng:
 * - `backend` khai `value: int`, nên một số lẻ lọt qua sẽ thành 422 chứ không
 *   phải một câu nói được cho người dùng.
 * - Ô `type=number` cho gõ `e`, `-` và dấu chấm, nên "chỉ cần đặt min/max trên
 *   input" là không đủ.
 * - Ngưỡng phần trăm > 100 tạo một cảnh báo **không bao giờ nổ**: nhận rồi im
 *   lặng thì người dùng ngồi đợi mãi một thông báo không tồn tại.
 */
describe('kiemNguongGia', () => {
  it('nhận số nguyên dương', () => {
    expect(kiemNguongGia(1)).toBeNull();
    expect(kiemNguongGia(199000)).toBeNull();
    // Không chặn trên: game AAA vài triệu đồng là chuyện bình thường.
    expect(kiemNguongGia(5_000_000)).toBeNull();
  });

  it('từ chối rỗng, 0, âm', () => {
    expect(kiemNguongGia(null)).not.toBeNull();
    expect(kiemNguongGia(0)).not.toBeNull();
    expect(kiemNguongGia(-1)).not.toBeNull();
  });

  it('từ chối số lẻ và giá trị không hữu hạn', () => {
    expect(kiemNguongGia(199000.5)).not.toBeNull();
    expect(kiemNguongGia(NaN)).not.toBeNull();
    expect(kiemNguongGia(Infinity)).not.toBeNull();
  });
});

describe('kiemPhanTram', () => {
  it('nhận 1..100', () => {
    expect(kiemPhanTram(1)).toBeNull();
    expect(kiemPhanTram(50)).toBeNull();
    // 100% là đợt tặng miễn phí — hợp lệ, không được chặn nhầm.
    expect(kiemPhanTram(100)).toBeNull();
  });

  it('từ chối 0 và trên 100', () => {
    expect(kiemPhanTram(0)).not.toBeNull();
    expect(kiemPhanTram(101)).not.toBeNull();
    expect(kiemPhanTram(120)).not.toBeNull();
  });

  it('từ chối rỗng, âm, số lẻ', () => {
    expect(kiemPhanTram(null)).not.toBeNull();
    expect(kiemPhanTram(-5)).not.toBeNull();
    expect(kiemPhanTram(49.5)).not.toBeNull();
  });
});
