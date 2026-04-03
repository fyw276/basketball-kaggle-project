import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'core/providers/auth_provider.dart';
import 'core/providers/theme_provider.dart';
import 'core/services/api_base_resolver.dart';
import 'core/services/api_client.dart';
import 'features/auth/screens/auth_screen.dart';
import 'features/shell/app_shell_screen.dart';
import 'features/home/screens/app_home_screen.dart';
import 'features/wardrobe/screens/wardrobe_screen.dart';
import 'features/analysis/screens/outfit_screen.dart';
import 'features/analysis/screens/similarity_screen.dart';
import 'features/analysis/screens/suitability_screen.dart';
import 'features/profile/screens/style_settings_screen.dart';

void main() {
  ErrorWidget.builder = (FlutterErrorDetails details) {
    return Material(
      color: Colors.white,
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: DefaultTextStyle(
            style: const TextStyle(
              fontFamily: 'monospace',
              fontSize: 12,
              color: Colors.red,
            ),
            child: Text(
              'Flutter ErrorWidget\n\n${details.exceptionAsString()}\n\n${details.stack ?? ''}',
            ),
          ),
        ),
      ),
    );
  };

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
  };

  runZonedGuarded(
    () => runApp(const ClothingAssistantApp()),
    (error, stack) {
      FlutterError.reportError(
        FlutterErrorDetails(exception: error, stack: stack),
      );
    },
  );
}

class ClothingAssistantApp extends StatelessWidget {
  const ClothingAssistantApp({super.key});

  @override
  Widget build(BuildContext context) {
    final apiClient = ApiClient(baseUrl: resolveApiBaseUrl());
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider(apiClient)),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
      ],
      child: const _AppRouterHost(),
    );
  }
}

class _AppRouterHost extends StatefulWidget {
  const _AppRouterHost();

  @override
  State<_AppRouterHost> createState() => _AppRouterHostState();
}

class _AppRouterHostState extends State<_AppRouterHost> {
  GoRouter? _router;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final auth = context.read<AuthProvider>();
    _router ??= GoRouter(
      initialLocation: '/auth',
      refreshListenable: auth,
      redirect: (context, state) {
        // Use the same auth instance captured above; avoid re-creating router
        // on every auth notify (can cause white screens on web).
        final isLoggedIn = auth.isAuthenticated;
        final isAuthRoute = state.matchedLocation == '/auth';
        if (!isLoggedIn && !isAuthRoute) return '/auth';
        if (isLoggedIn && isAuthRoute) return '/shell';
        return null;
      },
      routes: [
        GoRoute(
          path: '/auth',
          builder: (context, state) => const AuthScreen(),
        ),
        GoRoute(
          path: '/shell',
          builder: (context, state) => const AppShellScreen(),
        ),
        GoRoute(
          path: '/home',
          builder: (context, state) => const AppHomeScreen(),
        ),
        GoRoute(
          path: '/wardrobe',
          builder: (context, state) => const WardrobeScreen(),
        ),
        GoRoute(
          path: '/outfit',
          builder: (context, state) => const OutfitScreen(),
        ),
        GoRoute(
          path: '/similarity',
          builder: (context, state) => const SimilarityScreen(),
        ),
        GoRoute(
          path: '/suitability',
          builder: (context, state) => const SuitabilityScreen(),
        ),
        GoRoute(
          path: '/style-settings',
          builder: (context, state) => const StyleSettingsScreen(),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    return MaterialApp.router(
      title: 'AI 穿搭助手',
      debugShowCheckedModeBanner: false,
      theme: themeProvider.lightTheme,
      darkTheme: themeProvider.darkTheme,
      themeMode: themeProvider.themeMode,
      routerConfig: _router!,
      builder: (context, child) {
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.noScaling,
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
