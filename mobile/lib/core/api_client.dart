import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

final dioProvider = Provider<Dio>((ref) {
  final storage = ref.watch(secureStorageProvider);
  final dio = Dio(
    BaseOptions(
      // MOCK: Trỏ về server FastAPI localhost hoặc URL production sau này
      baseUrl: 'http://10.0.2.2:8000/api/v1',
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 3),
      headers: {
        'Content-Type': 'application/json',
      },
    ),
  );

  // Thêm Interceptor để xử lý Token hoặc Log
  dio.interceptors.add(InterceptorsWrapper(
    onRequest: (options, handler) async {
      final token = await storage.read(key: 'jwt_token');
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      return handler.next(options);
    },
    onError: (DioException e, handler) async {
      if (e.response?.statusCode == 401) {
        // Token hết hạn hoặc không hợp lệ, xóa token
        await storage.delete(key: 'jwt_token');
      }
      return handler.next(e);
    },
  ));

  return dio;
});

// Ví dụ một Repository dùng Dio
class GameRepository {
  final Dio _dio;

  GameRepository(this._dio);

  Future<List<dynamic>> getDeals() async {
    try {
      final response = await _dio.get('/prices/deals');
      return response.data['deals'] as List<dynamic>;
    } catch (e) {
      // MOCK Data nếu server đang tắt để app không crash
      return [
        {"game_id": "elden-ring", "discount_percent": 30, "price_vnd": 595000, "is_historical_low": true}
      ];
    }
  }

  Future<List<dynamic>> getFreeGames() async {
    try {
      final response = await _dio.get('/prices/free-games');
      return response.data['free_games'] as List<dynamic>;
    } catch (e) {
      // MOCK Data
      return [
        {"game_id": "marvels-midnight-suns", "is_free_promo": true, "promo_ends_at": "2026-09-12"}
      ];
    }
  }
}

final gameRepositoryProvider = Provider<GameRepository>((ref) {
  return GameRepository(ref.watch(dioProvider));
});
