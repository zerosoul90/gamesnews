import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:dio/dio.dart';
import 'api_client.dart';

// MOCK: Đại diện cho thư viện firebase_messaging
class MockFirebaseMessaging {
  static Future<void> requestPermission() async {
    debugPrint("Firebase: Đã xin quyền Push Notification thành công");
  }

  static Future<String?> getToken() async {
    return "mock_device_fcm_token_12345";
  }

  static void onMessageOpenedApp(Function(Map<String, dynamic> data) handler) {
    // Giả lập người dùng bấm vào một thông báo "Elden Ring đang giảm 30%"
    Future.delayed(const Duration(seconds: 15), () {
      debugPrint("Firebase: Giả lập người dùng vừa chạm vào thông báo!");
      handler({
        'type': 'PRICE_ALERT',
        'game_id': 'elden-ring'
      });
    });
  }
}

final notificationServiceProvider = Provider<NotificationService>((ref) {
  return NotificationService(ref.watch(dioProvider));
});

class NotificationService {
  final Dio _dio;

  NotificationService(this._dio);
  void initialize(GoRouter router) async {
    await MockFirebaseMessaging.requestPermission();
    final token = await MockFirebaseMessaging.getToken();
    debugPrint("Firebase Token: $token");
    
    // Path đầy đủ: baseUrl giờ là gốc API, không còn kèm `/api/v1`. Router
    // `user` là một trong ít router thật sự nằm dưới prefix đó.
    if (token != null) {
      try {
        await _dio.post('/api/v1/user/device',
            data: {'fcm_token': token, 'device_type': 'android'});
        debugPrint("Gửi FCM token thành công");
      } catch (e) {
        debugPrint("Lỗi gửi FCM token: $e");
      }
    }

    // Xử lý khi user bấm vào thông báo từ background
    MockFirebaseMessaging.onMessageOpenedApp((data) {
      if (data['type'] == 'PRICE_ALERT') {
        final gameId = data['game_id'];
        if (gameId != null) {
          debugPrint("Điều hướng tới màn hình game: $gameId");
          router.push('/game/$gameId');
        }
      }
    });
  }
}
