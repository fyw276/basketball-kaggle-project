import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../analysis/screens/outfit_recommend_screen.dart';
import '../../analysis/screens/similarity_analysis_screen.dart';
import '../../analysis/screens/suitability_analysis_screen.dart';
import '../../analysis/screens/body_shape_insight_screen.dart';
import '../../analysis/screens/mood_outfit_screen.dart';
import '../../analysis/screens/virtual_tryon_screen.dart';

/// 智能穿搭：功能入口（列表 + 右侧箭头）。
/// 顺序：智能推荐 → 情绪穿搭 → 虚拟试衣 → …
class OutfitHubScreen extends StatelessWidget {
  const OutfitHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('智能穿搭'),
        centerTitle: true,
        backgroundColor: palette.background,
        foregroundColor: palette.textTitle,
        surfaceTintColor: Colors.transparent,
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        children: [
          _HubTile(
            icon: Icons.auto_awesome,
            title: '智能推荐',
            subtitle: '上传服装图片，智能推荐搭配方案',
            onTap: () => _pushPage(context, const OutfitRecommendScreen()),
          ),
          _HubTile(
            icon: Icons.favorite_outline,
            title: '情绪穿搭',
            subtitle: '根据心情推荐颜色与风格，并匹配衣橱单品',
            onTap: () => _pushPage(context, const MoodOutfitScreen()),
          ),
          _HubTile(
            icon: Icons.view_in_ar,
            title: '虚拟试衣',
            subtitle: 'AI 生成正面 / 侧面 / 背面伪 3D 效果',
            onTap: () => _pushPage(context, const VirtualTryonScreen()),
          ),
          _HubTile(
            icon: Icons.layers_outlined,
            title: '相似衣物检测',
            subtitle: '检测衣橱中相似的服装，避免重复购买',
            onTap: () => _pushPage(context, const SimilarityAnalysisScreen()),
          ),
          _HubTile(
            icon: Icons.bar_chart_rounded,
            title: '适合度分析',
            subtitle: '分析服装与您的匹配程度',
            onTap: () => _pushPage(context, const SuitabilityAnalysisScreen()),
          ),
          _HubTile(
            icon: Icons.accessibility_new_outlined,
            title: '体型感知',
            subtitle: '根据您的体型推荐最适合的穿搭',
            onTap: () => _pushPage(context, const BodyShapeInsightScreen()),
          ),
        ],
      ),
    );
  }

  void _pushPage(BuildContext context, Widget page) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => page),
    );
  }
}

class _HubTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _HubTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      color: palette.cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: palette.divider),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: palette.primary.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: palette.primary, size: 26),
        ),
        title: Text(
          title,
          style: TextStyle(
            fontWeight: FontWeight.w700,
            fontSize: 16,
            color: palette.textTitle,
          ),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(
            subtitle,
            style: TextStyle(
              fontSize: 13,
              color: palette.textBody,
              height: 1.35,
            ),
          ),
        ),
        trailing: Icon(Icons.chevron_right, color: palette.textBody),
        onTap: onTap,
      ),
    );
  }
}
