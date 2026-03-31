import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../home/screens/outfit_hub_screen.dart';
import '../profile/screens/personal_settings_screen.dart';
import '../wardrobe/screens/wardrobe_screen.dart';
import '../../core/providers/theme_provider.dart';
import '../../core/widgets/global_gender_expression_bar.dart';

/// 主导航：底部三栏 — 衣橱 / 穿搭 / 设置
/// 底部固定显示全局性别表达指数滑块，拖动时实时切换全局配色。
class AppShellScreen extends StatefulWidget {
  const AppShellScreen({super.key});

  @override
  State<AppShellScreen> createState() => _AppShellScreenState();
}

class _AppShellScreenState extends State<AppShellScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;

    return Scaffold(
      body: IndexedStack(
        index: _index,
        sizing: StackFit.expand,
        children: const [
          WardrobeScreen(),
          OutfitHubScreen(),
          PersonalSettingsScreen(),
        ],
      ),
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 性别表达滑块（实时切换全局配色）
          GlobalGenderExpressionBar(),
          // 三栏导航
          NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => setState(() => _index = i),
            backgroundColor: palette.surface,
            indicatorColor: palette.primary.withValues(alpha: 0.18),
            surfaceTintColor: Colors.transparent,
            labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.checkroom_outlined),
                selectedIcon: Icon(Icons.checkroom),
                label: '衣橱',
              ),
              NavigationDestination(
                icon: Icon(Icons.auto_awesome_outlined),
                selectedIcon: Icon(Icons.auto_awesome),
                label: '穿搭',
              ),
              NavigationDestination(
                icon: Icon(Icons.person_outline),
                selectedIcon: Icon(Icons.person),
                label: '设置',
              ),
            ],
          ),
        ],
      ),
    );
  }
}
