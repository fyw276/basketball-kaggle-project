import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/gender_decoration.dart';
import '../../analysis/screens/body_shape_insight_screen.dart';
import '../../analysis/screens/mood_outfit_screen.dart';
import '../../analysis/screens/outfit_recommend_screen.dart';
import '../../analysis/screens/smart_outfit_screen.dart';
import '../../analysis/screens/similarity_analysis_screen.dart';
import '../../analysis/screens/suitability_analysis_screen.dart';
import '../../analysis/screens/virtual_tryon_screen.dart';
import '../../wardrobe/screens/wardrobe_screen.dart';

/// 主页：功能入口列表；配色随全局性别表达指数；底部滑块仅在 Shell 中展示。
class AppHomeScreen extends StatelessWidget {
  const AppHomeScreen({super.key});

  static const _radius = 26.0;

  void _push(BuildContext context, Widget page) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;

    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('智能穿搭助手'),
        backgroundColor: palette.background,
        foregroundColor: palette.textTitle,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            tooltip: '退出登录',
            icon: Icon(Icons.logout_rounded, color: palette.textBody),
            onPressed: () {
              context.read<AuthProvider>().logout();
              context.go('/auth');
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          Positioned(
            right: -64,
            bottom: 96,
            child: Opacity(
              opacity: 0.1,
              child: Consumer<ThemeProvider>(
                builder: (context, tp, _) {
                  return GenderDecoration(
                    genderExpression: tp.genderExpression,
                    size: 300,
                  );
                },
              ),
            ),
          ),
          ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
            children: [
              Text(
                'AI 穿搭，自由表达',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: palette.textTitle,
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                '智能衣橱・虚拟试衣・风格自由',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: palette.textBody,
                    ),
              ),
              const SizedBox(height: 8),
              Consumer<AuthProvider>(
                builder: (context, auth, _) {
                  return Text(
                    '你好，${auth.username ?? '用户'}',
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: palette.textBody,
                        ),
                  );
                },
              ),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: palette.cardBg,
                  borderRadius: BorderRadius.circular(_radius),
                  border: Border.all(color: palette.divider),
                  boxShadow: palette.cardShadows,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.tips_and_updates_outlined,
                            color: palette.primary, size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '今天先做什么',
                          style:
                              Theme.of(context).textTheme.titleMedium?.copyWith(
                                    color: palette.textTitle,
                                    fontWeight: FontWeight.w800,
                                  ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '从衣橱整理开始，再去做推荐、试衣和适合度分析，整条链路会更顺。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: palette.textBody,
                            height: 1.4,
                          ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _QuickActionChip(
                          palette: palette,
                          icon: Icons.checkroom_outlined,
                          label: '我的衣橱',
                          onTap: () => _push(context, const WardrobeScreen()),
                        ),
                        _QuickActionChip(
                          palette: palette,
                          icon: Icons.view_in_ar_rounded,
                          label: '虚拟试衣',
                          onTap: () =>
                              _push(context, const VirtualTryonScreen()),
                        ),
                        _QuickActionChip(
                          palette: palette,
                          icon: Icons.auto_awesome_rounded,
                          label: '智能穿搭',
                          onTap: () =>
                              _push(context, const SmartOutfitScreen()),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.auto_awesome_rounded,
                title: '智能穿搭',
                subtitle: '参考图 + 自动天气与可选心情，一次生成 3 套衣橱搭配',
                onTap: () => _push(context, const SmartOutfitScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.view_day_outlined,
                title: '穿搭推荐',
                subtitle: '选择场景并上传图片，生成更贴近场景的搭配建议',
                onTap: () => _push(context, const OutfitRecommendScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.favorite_outline_rounded,
                title: '情绪穿搭',
                subtitle: '按当前心情推荐颜色和风格，并匹配衣橱单品',
                onTap: () => _push(context, const MoodOutfitScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.view_in_ar_rounded,
                title: '虚拟试衣',
                subtitle: '伪 3D 多角度（正面 / 侧面 / 背面）',
                onTap: () => _push(context, const VirtualTryonScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.layers_outlined,
                title: '相似衣物检测',
                subtitle: '对比衣橱，避免重复购买',
                onTap: () => _push(context, const SimilarityAnalysisScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.bar_chart_rounded,
                title: '适合度分析',
                subtitle: '肤色、体型与风格匹配度',
                onTap: () => _push(context, const SuitabilityAnalysisScreen()),
              ),
              const SizedBox(height: 12),
              _HomeRow(
                palette: palette,
                radius: _radius,
                icon: Icons.accessibility_new_rounded,
                title: '体型感知',
                subtitle: '结合身高体型与偏好，给出可执行穿搭方向',
                onTap: () => _push(context, const BodyShapeInsightScreen()),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _QuickActionChip extends StatelessWidget {
  final Palette palette;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _QuickActionChip({
    required this.palette,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        decoration: BoxDecoration(
          color: palette.primary.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: palette.primary.withValues(alpha: 0.16)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: palette.primary),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: palette.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HomeRow extends StatelessWidget {
  final Palette palette;
  final double radius;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _HomeRow({
    required this.palette,
    required this.radius,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: palette.cardBg,
      borderRadius: BorderRadius.circular(radius),
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(radius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(radius),
            border: Border.all(color: palette.divider),
            boxShadow: palette.cardShadows,
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: palette.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Icon(icon, size: 28, color: palette.primary),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w800,
                            color: palette.textTitle,
                          ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: palette.textBody,
                            height: 1.35,
                          ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: palette.textBody),
            ],
          ),
        ),
      ),
    );
  }
}
