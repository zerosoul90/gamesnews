/**
 * Kiểm giá trị ngưỡng cảnh báo.
 *
 * Tách khỏi component để test được các biên (0, số lẻ, 101) mà không phải dựng
 * cả `GameComponent` với chục dependency của nó. Trả về thông báo lỗi tiếng
 * Việt, hoặc `null` khi hợp lệ.
 *
 * Kiểm ở client không phải để tin client — backend vẫn khai `value: int` và tự
 * từ chối. Nó ở đây để người dùng nhận một câu nói rõ vấn đề, thay vì một cục
 * 422 của Pydantic.
 */

/** Mức giá: số nguyên dương. Không chặn trên — game AAA có thể vài triệu đồng. */
export function kiemNguongGia(value: number | null): string | null {
  if (value === null || !Number.isFinite(value) || !Number.isInteger(value) || value <= 0) {
    return 'Nhập một mức giá nguyên, lớn hơn 0.';
  }
  return null;
}

/**
 * Phần trăm giảm: số nguyên 1..100.
 *
 * Chặn trên là 100 vì `discount_percent` của mọi store đều nằm trong 0..100 —
 * đặt 120 là một cảnh báo không bao giờ nổ, mà nhận rồi im lặng thì còn tệ hơn
 * từ chối thẳng.
 */
export function kiemPhanTram(value: number | null): string | null {
  if (
    value === null ||
    !Number.isFinite(value) ||
    !Number.isInteger(value) ||
    value <= 0 ||
    value > 100
  ) {
    return 'Nhập một số nguyên từ 1 đến 100.';
  }
  return null;
}
