import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:dio/dio.dart';
import 'api_client.dart';

/// Đăng ký thiết bị nhận push và điều hướng khi người dùng chạm thông báo.
///
/// **Bản trước là một cái mock giả dạng bản thật**, và nó gây ra ba chuyện —
/// chuyện thứ ba tệ nhất:
///
/// 1. `getToken()` trả chuỗi cứng `"mock_device_fcm_token_12345"`, rồi POST
///    thẳng lên `/api/v1/user/device`. Server ghi nhận đó là một thiết bị
///    thật: `tokens_of()` trả về nó và `send_push_notification` đếm nó vào số
///    máy nhận được. Mọi tầng phía trên tin rằng người dùng có thiết bị.
/// 2. Điều kiện điều hướng `data['type'] == 'PRICE_ALERT'` **không bao giờ
///    khớp** phản hồi thật. `adapters/fcm/adapter.py` chỉ đẩy `payload.data`
///    vào tin nhắn, mà với cảnh báo giá `data` là
///    `{"game_id": ..., "store": ...}` — không có khoá `type` nào cả, và
///    `NotificationPayload.type` thì viết thường.
/// 3. `onMessageOpenedApp` hẹn giờ 15 giây rồi **tự điều hướng** sang
///    `/game/elden-ring`. Trong một bản build giao tới người dùng, cứ 15 giây
///    sau khi mở app là màn hình tự nhảy sang một game viết cứng. Đây không
///    còn là dữ liệu giả nữa mà là hành vi giả, và nó chạy ở mọi phiên.
///
/// Nay: chưa có Firebase thì **không đăng ký gì cả**. Không token giả, không
/// điều hướng tự phát. Cùng nguyên tắc với `PushService` bên web.
class NotificationService {
  final Dio _dio;

  NotificationService(this._dio);

  /// Lấy token FCM của máy này.
  ///
  /// Trả `null` chừng nào dự án chưa có Firebase — `pubspec.yaml` không có
  /// `firebase_core`/`firebase_messaging`, và thêm chúng vào mà thiếu
  /// `google-services.json` (Android) hoặc `GoogleService-Info.plist` (iOS)
  /// thì hỏng ngay ở bước build, không phải lúc chạy.
  ///
  /// Khi nối Firebase thật, thay đúng thân hàm này:
  /// ```dart
  /// await Firebase.initializeApp();
  /// return FirebaseMessaging.instance.getToken();
  /// ```
  /// và nhớ xin quyền trước trên iOS.
  Future<String?> layFcmToken() async {
    return null;
  }

  /// Đăng ký thiết bị với server. Không có token thì dừng, không gửi gì.
  void initialize(GoRouter router) async {
    final token = await layFcmToken();

    if (token == null) {
      debugPrint(
        'Push: chưa cấu hình Firebase nên không đăng ký thiết bị. '
        'Xem layFcmToken() trong notification_service.dart.',
      );
      return;
    }

    try {
      // `baseUrl` là gốc API, không kèm `/api/v1`. Router `user` là một trong
      // số ít router thật sự nằm dưới prefix đó.
      await _dio.post(
        '/api/v1/user/device',
        data: {'fcm_token': token, 'device_type': 'android'},
      );
      debugPrint('Push: đã đăng ký thiết bị');
    } catch (e) {
      debugPrint('Push: đăng ký thiết bị hỏng: $e');
    }
  }

  /// Điều hướng khi người dùng chạm vào một thông báo.
  ///
  /// Tách ra thành hàm công khai để phần nối Firebase sau này gọi thẳng, và để
  /// kiểm được mà không cần cả tầng messaging.
  ///
  /// Khớp theo `game_id` chứ không theo `type`: `type` không có mặt trong
  /// `data` của cảnh báo giá (xem chú thích lớp ở trên). Route mobile là
  /// `/game/:id` và backend gửi `game_id` dạng ObjectId — khác web, vốn dùng
  /// slug.
  void xuLyChamThongBao(GoRouter router, Map<String, dynamic> data) {
    final gameId = data['game_id'];
    if (gameId is String && gameId.isNotEmpty) {
      router.push('/game/$gameId');
    }
  }
}

final notificationServiceProvider = Provider<NotificationService>((ref) {
  return NotificationService(ref.watch(dioProvider));
});
