import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile/core/notification_service.dart';

void main() {
  runApp(
    const ProviderScope(
      child: GameNewsApp(),
    ),
  );
}

// ================= ROUTING =================
final _rootNavigatorKey = GlobalKey<NavigatorState>();
final _shellNavigatorKey = GlobalKey<NavigatorState>();

final router = GoRouter(
  navigatorKey: _rootNavigatorKey,
  initialLocation: '/',
  routes: [
    ShellRoute(
      navigatorKey: _shellNavigatorKey,
      builder: (context, state, child) {
        return ScaffoldWithBottomNavBar(child: child);
      },
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const HomeScreen(),
        ),
        GoRoute(
          path: '/search',
          builder: (context, state) => const SearchScreen(),
        ),
        GoRoute(
          path: '/library',
          builder: (context, state) => const LibraryScreen(),
        ),
        GoRoute(
          path: '/settings',
          builder: (context, state) => const SettingsScreen(),
        ),
      ],
    ),
    GoRoute(
      parentNavigatorKey: _rootNavigatorKey,
      path: '/game/:id',
      builder: (context, state) {
        final id = state.pathParameters['id']!;
        return GameDetailScreen(gameId: id);
      },
    ),
  ],
);

// ================= APP WIDGET =================
class GameNewsApp extends ConsumerStatefulWidget {
  const GameNewsApp({super.key});

  @override
  ConsumerState<GameNewsApp> createState() => _GameNewsAppState();
}

class _GameNewsAppState extends ConsumerState<GameNewsApp> {
  @override
  void initState() {
    super.initState();
    // Khởi tạo Firebase Messaging (Mock) và truyền router vào để điều hướng
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(notificationServiceProvider).initialize(router);
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'GameNews',
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF0F172A),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF2563EB),
          surface: Color(0xFF1E293B),
        ),
      ),
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}

// ================= BOTTOM NAV BAR =================
class ScaffoldWithBottomNavBar extends StatelessWidget {
  const ScaffoldWithBottomNavBar({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    int currentIndex = _calculateSelectedIndex(location);

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: currentIndex,
        onDestinationSelected: (int index) {
          switch (index) {
            case 0:
              context.go('/');
              break;
            case 1:
              context.go('/search');
              break;
            case 2:
              context.go('/library');
              break;
            case 3:
              context.go('/settings');
              break;
          }
        },
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Khám phá'),
          NavigationDestination(icon: Icon(Icons.search_outlined), selectedIcon: Icon(Icons.search), label: 'Tìm kiếm'),
          NavigationDestination(icon: Icon(Icons.library_books_outlined), selectedIcon: Icon(Icons.library_books), label: 'Thư viện'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Cài đặt'),
        ],
      ),
    );
  }

  static int _calculateSelectedIndex(String location) {
    if (location.startsWith('/search')) return 1;
    if (location.startsWith('/library')) return 2;
    if (location.startsWith('/settings')) return 3;
    return 0; // Default: Home
  }
}

// ================= PLACEHOLDER SCREENS =================
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('GameNews', style: TextStyle(fontWeight: FontWeight.bold))),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('🔥 Top Deals & Free Games tuần này'),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () => context.push('/game/elden-ring'),
              child: const Text('Xem chi tiết Elden Ring'),
            )
          ],
        ),
      ),
    );
  }
}

class SearchScreen extends StatelessWidget {
  const SearchScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tìm kiếm')),
      body: const Center(child: Text('🔍 Tìm kiếm Real-time (Meilisearch)')),
    );
  }
}

class LibraryScreen extends StatelessWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Thư viện của tôi')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('Vui lòng kết nối tài khoản Steam'),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.login),
              label: const Text('Đăng nhập bằng Steam'),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.black, foregroundColor: Colors.white),
            )
          ],
        ),
      ),
    );
  }
}

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Cài đặt')),
      body: ListView(
        children: const [
          ListTile(
            leading: Icon(Icons.notifications_active),
            title: Text('Cài đặt thông báo (Gatekeeper)'),
            subtitle: Text('Bật/tắt giờ đi ngủ, mức giá cảnh báo'),
            trailing: Icon(Icons.chevron_right),
          )
        ],
      ),
    );
  }
}

// ================= GAME DETAIL (NO BOTTOM BAR) =================
class GameDetailScreen extends StatelessWidget {
  final String gameId;
  const GameDetailScreen({super.key, required this.gameId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(gameId.toUpperCase()),
      ),
      body: ListView(
        children: [
          Container(
            height: 200,
            color: Colors.blueGrey,
            child: const Center(child: Text('Ảnh Cover', style: TextStyle(color: Colors.white))),
          ),
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Giá rẻ nhất', style: TextStyle(fontSize: 16, color: Colors.grey)),
                const Text('595.000₫', style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.greenAccent)),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: () {},
                    icon: const Icon(Icons.notifications),
                    label: const Text('Theo dõi giảm giá'),
                  ),
                ),
                const SizedBox(height: 24),
                const Text('Biểu đồ lịch sử giá', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                Container(
                  height: 150,
                  margin: const EdgeInsets.only(top: 8),
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.grey.shade800),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Center(child: Text('Đang vẽ biểu đồ...')),
                )
              ],
            ),
          )
        ],
      ),
    );
  }
}
