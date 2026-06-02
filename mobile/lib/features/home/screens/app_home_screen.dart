import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/platform_image.dart';
import '../../../core/widgets/gender_decoration.dart';
import '../../analysis/screens/body_shape_insight_screen.dart';
import '../../analysis/screens/mood_outfit_screen.dart';
import '../../analysis/screens/outfit_recommend_screen.dart';
import '../../analysis/screens/smart_outfit_screen.dart';
import '../../analysis/screens/similarity_analysis_screen.dart';
import '../../analysis/screens/suitability_analysis_screen.dart';
import '../../analysis/screens/virtual_tryon_screen.dart';
import '../../agent/screens/agent_chat_screen.dart';
import '../../wardrobe/screens/wardrobe_screen.dart';

/// 主页：功能入口列表；配色随全局性别表达指数；底部滑块仅在 Shell 中展示。
class AppHomeScreen extends StatefulWidget {
  const AppHomeScreen({super.key});

  @override
  State<AppHomeScreen> createState() => _AppHomeScreenState();
}

class _AppHomeScreenState extends State<AppHomeScreen> {
  static const _radius = 26.0;

  bool _homeLoading = true;
  String _city = '定位中';
  String _weather = '晴';
  double _temp = 20;
  Map<String, dynamic> _todayRec = const {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadHomeCards();
    });
  }

  bool _isSameLocalDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }

  Future<void> _loadHomeCards() async {
    if (!mounted) return;
    final auth = context.read<AuthProvider>();
    final apiClient = auth.apiClient;
    final isAuthenticated = auth.isAuthenticated;
    setState(() => _homeLoading = true);
    try {
      final prefs = await SharedPreferences.getInstance();
      var city = prefs.getString('smart_outfit_city_short') ?? '';
      final fullAddress =
          (prefs.getString('smart_outfit_full_address') ?? '').trim();
      var displayLocation = city.trim().isNotEmpty ? city.trim() : fullAddress;
      var weather = prefs.getString('smart_outfit_weather') ?? '晴';
      var temp = prefs.getDouble('smart_outfit_temp') ?? 20;

      final recRaw = prefs.getString('home_today_recommendation_json') ??
          prefs.getString('home_today_recommendation') ??
          '{}';
      Map<String, dynamic> rec = const {};
      try {
        final decoded = jsonDecode(recRaw);
        if (decoded is Map) rec = Map<String, dynamic>.from(decoded);
      } catch (_) {}
      if (rec.isNotEmpty) {
        final updated = DateTime.tryParse(rec['updated_at']?.toString() ?? '');
        if (updated == null ||
            !_isSameLocalDay(updated.toLocal(), DateTime.now())) {
          rec = {};
          await prefs.remove('home_today_recommendation');
          await prefs.remove('home_today_recommendation_json');
        }
      }

      final weatherQuery = city.trim().isNotEmpty ? city.trim() : fullAddress;
      if (isAuthenticated && weatherQuery.isNotEmpty) {
        final live = await apiClient.getSmartOutfitWeatherByCity(weatherQuery);
        if (live['error'] == null) {
          city = (live['city']?.toString().trim().isNotEmpty ?? false)
              ? live['city'].toString().trim()
              : city;
          displayLocation = city.trim().isNotEmpty
              ? city.trim()
              : (live['display_address']?.toString().trim().isNotEmpty ?? false)
                  ? live['display_address'].toString().trim()
                  : displayLocation;
          weather = live['weather']?.toString() ?? weather;
          temp = (live['temperature'] as num?)?.toDouble() ?? temp;
        }
      }

      if (!mounted) return;
      setState(() {
        _city = displayLocation.isNotEmpty ? displayLocation : '未定位';
        _weather = weather;
        _temp = temp;
        _todayRec = rec;
        _homeLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _homeLoading = false);
    }
  }

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
              if (_homeLoading) _HomeTopSkeleton(palette: palette),
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
                        Icon(Icons.location_on_outlined,
                            color: palette.primary, size: 18),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            '$_city · $_weather ${_temp.toStringAsFixed(0)}℃',
                            style: TextStyle(
                              color: palette.textTitle,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: '刷新',
                          onPressed: _homeLoading ? null : _loadHomeCards,
                          icon: Icon(Icons.refresh_rounded,
                              size: 18, color: palette.primary),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    _TodayRecommendCard(
                      palette: palette,
                      apiBase: context.read<AuthProvider>().apiClient.baseUrl,
                      loading: _homeLoading,
                      rec: _todayRec,
                      onOneTap: () => _push(context,
                          const SmartOutfitScreen(autoPickAndGenerate: true)),
                      onViewDetail: () => _push(
                        context,
                        SmartOutfitScreen(
                          initialResultIndex:
                              (_todayRec['recommendation_index'] is num)
                                  ? (_todayRec['recommendation_index'] as num)
                                      .toInt()
                                  : 0,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
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
                        _QuickActionChip(
                          palette: palette,
                          icon: Icons.bolt_rounded,
                          label: '一键生成',
                          onTap: () => _push(
                            context,
                            const SmartOutfitScreen(autoPickAndGenerate: true),
                          ),
                        ),
                        _QuickActionChip(
                          palette: palette,
                          icon: Icons.chat_bubble_outline_rounded,
                          label: '问助手',
                          onTap: () => _push(context, const AgentChatScreen()),
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
                icon: Icons.support_agent_rounded,
                title: 'AI 穿搭助手',
                subtitle: '用对话串联衣橱、推荐、天气、试衣和反馈',
                onTap: () => _push(context, const AgentChatScreen()),
              ),
              const SizedBox(height: 12),
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

class _TodayRecommendCard extends StatelessWidget {
  final Palette palette;
  final String apiBase;
  final bool loading;
  final Map<String, dynamic> rec;
  final VoidCallback onOneTap;
  final VoidCallback onViewDetail;

  const _TodayRecommendCard({
    required this.palette,
    required this.apiBase,
    required this.loading,
    required this.rec,
    required this.onOneTap,
    required this.onViewDetail,
  });

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const _TodayCardSkeleton();
    }

    final hasRec = rec.isNotEmpty;
    final previewRaw = rec['preview_image_url']?.toString();
    final previewUrl =
        hasRec ? resolveGarmentImageUrl(previewRaw, apiBase) : null;

    if (!hasRec) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: palette.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: palette.divider),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  '今日推荐',
                  style: TextStyle(
                    color: palette.textTitle,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: palette.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '待生成',
                    style: TextStyle(
                      color: palette.primary,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const Spacer(),
                TextButton.icon(
                  onPressed: onOneTap,
                  icon: const Icon(Icons.bolt_rounded, size: 16),
                  label: const Text('一键生成'),
                ),
              ],
            ),
            Text(
              '暂无今日推荐，点击一键生成获取个性化搭配。',
              style: TextStyle(color: palette.textBody, fontSize: 12),
            ),
          ],
        ),
      );
    }

    final aiRaw = rec['ai_recommendation'];
    final ai = aiRaw is Map ? Map<String, dynamic>.from(aiRaw) : const {};
    final style = ai['style']?.toString() ?? '简约';
    final score = (ai['score'] is num)
        ? (ai['score'] as num).toDouble()
        : double.tryParse('${ai['score']}') ?? 0;
    final reasonsRaw = ai['reasons'];
    final reasons = reasonsRaw is List
        ? reasonsRaw
            .map((e) => e.toString().trim())
            .where((e) => e.isNotEmpty)
            .take(3)
            .toList()
        : <String>[];
    final desc = rec['description']?.toString() ?? '';
    final recIndex = (rec['recommendation_index'] is num)
        ? (rec['recommendation_index'] as num).toInt().clamp(0, 999)
        : 0;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                '今日推荐',
                style: TextStyle(
                  color: palette.textTitle,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: palette.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '评分 ${score.toStringAsFixed(1)}',
                  style: TextStyle(
                    color: palette.primary,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const Spacer(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  TextButton.icon(
                    onPressed: onViewDetail,
                    icon: const Icon(Icons.open_in_new_rounded, size: 16),
                    label: const Text('查看详情'),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.my_location_rounded,
                        size: 12,
                        color: palette.textBody.withValues(alpha: 0.7),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '将定位到上次浏览',
                        style: TextStyle(
                          fontSize: 10,
                          color: palette.textBody.withValues(alpha: 0.72),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: SizedBox(
                  width: 64,
                  height: 84,
                  child: PlatformImage(
                    networkUrl: previewUrl,
                    fit: BoxFit.cover,
                    placeholder: Container(
                      color: palette.surface,
                      alignment: Alignment.center,
                      child: Icon(
                        Icons.checkroom_outlined,
                        color: palette.primary,
                        size: 24,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '风格：$style',
                      style: TextStyle(color: palette.textBody, fontSize: 12),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '上次看到：搭配 ${recIndex + 1}',
                      style: TextStyle(
                        color: palette.textBody.withValues(alpha: 0.86),
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 4),
                    if (desc.isNotEmpty)
                      Text(
                        desc,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: palette.textBody,
                          fontSize: 12,
                          height: 1.3,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (reasons.isEmpty)
            Text(
              '暂无推荐理由，请点击“查看详情”查看完整搭配。',
              style: TextStyle(color: palette.textBody, fontSize: 12),
            )
          else
            ...reasons.map(
              (r) => Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  '- $r',
                  style: TextStyle(
                    color: palette.textBody,
                    fontSize: 12,
                    height: 1.3,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _HomeTopSkeleton extends StatelessWidget {
  final Palette palette;

  const _HomeTopSkeleton({required this.palette});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: palette.cardBg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: palette.divider),
        ),
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SkeletonBar(width: 180),
            SizedBox(height: 8),
            _SkeletonBar(width: 120),
          ],
        ),
      ),
    );
  }
}

class _TodayCardSkeleton extends StatelessWidget {
  const _TodayCardSkeleton();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SkeletonBar(width: 140),
        SizedBox(height: 8),
        _SkeletonBar(width: 220),
        SizedBox(height: 8),
        _SkeletonBar(width: 200),
      ],
    );
  }
}

class _SkeletonBar extends StatefulWidget {
  final double width;

  const _SkeletonBar({required this.width});

  @override
  State<_SkeletonBar> createState() => _SkeletonBarState();
}

class _SkeletonBarState extends State<_SkeletonBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
    _opacity = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    ).drive(Tween(begin: 0.38, end: 0.82));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: Container(
        width: widget.width,
        height: 12,
        decoration: BoxDecoration(
          color: Colors.black.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(999),
        ),
      ),
    );
  }
}
