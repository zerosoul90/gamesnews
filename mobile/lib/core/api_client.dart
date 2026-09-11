import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final secureStorageProvider = Provider<FlutterSecureStorage>((ref) {
  return const FlutterSecureStorage();
});

/// Gốc của API, KHÔNG kèm `/api/v1`.
///
/// Backend không gắn prefix đồng nhất: `/deals`, `/free-games`, `/search`,
/// `/games/...` nằm ở root, còn `user`, `auth` và `seo` mới ở `/api/v1`. Đặt
/// baseUrl là `/api/v1` thì mọi route root thành 404, nên base phải là gốc và
/// từng lời gọi tự mang path thật của nó.
///
/// Đổi khi build: `--dart-define=API_BASE_URL=https://...`. Mặc định là
/// `10.0.2.2:8000`, alias host của emulator Android — chỉ đúng trên máy dev, và
/// nếu viết cứng thì muốn deploy phải sửa code.
const apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

final dioProvider = Provider<Dio>((ref) {
  final storage = ref.watch(secureStorageProvider);
  final dio = Dio(
    BaseOptions(
      baseUrl: apiBaseUrl,
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

class GameRepository {
  final Dio _dio;

  GameRepository(this._dio);

  /// Lỗi được để nguyên cho người gọi, KHÔNG trả dữ liệu bịa.
  ///
  /// Bản trước bọc `catch (e)` rồi trả về một deal Elden Ring 595.000₫ viết
  /// cứng "để app không crash". Hệ quả: path `/prices/deals` vốn không tồn tại
  /// (route thật là `/deals`) vẫn cho ra một màn hình trông bình thường, nên
  /// không có cách nào phát hiện nó sai — và người dùng đọc một mức giá bịa như
  /// thể là giá thật. `AsyncValue` của Riverpod đã có sẵn nhánh lỗi để hiển thị
  /// "không tải được"; đó mới là chỗ xử lý việc này.
  Future<List<dynamic>> getDeals() async {
    final response = await _dio.get('/deals');
    return response.data['deals'] as List<dynamic>;
  }

  Future<List<dynamic>> getFreeGames() async {
    final response = await _dio.get('/free-games');
    return response.data['free_games'] as List<dynamic>;
  }
}

final gameRepositoryProvider = Provider<GameRepository>((ref) {
  return GameRepository(ref.watch(dioProvider));
});
