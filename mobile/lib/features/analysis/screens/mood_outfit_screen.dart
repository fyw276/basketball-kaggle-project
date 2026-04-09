import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/platform_image.dart';

/// 根据当前情绪给出穿搭方向，并从衣橱中匹配单品（后端 `/mood/recommend`）。
class MoodOutfitScreen extends StatefulWidget {
  const MoodOutfitScreen({super.key});

  @override
  State<MoodOutfitScreen> createState() => _MoodOutfitScreenState();
}

class _MoodOutfitScreenState extends State<MoodOutfitScreen> {
  List<dynamic> _quick = [];

  /// 快捷项下标（避免同一 mood 值两项同时高亮）
  int? _selectedQuickIndex;
  Map<String, dynamic>? _result;
  bool _loading = false;
  bool _loadingQuick = true;

  @override
  void initState() {
    super.initState();
    _loadQuick();
  }

  Future<void> _loadQuick() async {
    final auth = context.read<AuthProvider>();
    final raw = await auth.apiClient.getMoodQuickRecall();
    if (!mounted) return;
    setState(() {
      _loadingQuick = false;
      if (raw is List) {
        _quick = raw;
        if (_quick.isNotEmpty) _selectedQuickIndex = 0;
      }
    });
  }

  Future<void> _go() async {
    if (_selectedQuickIndex == null || _quick.isEmpty) {
      showAppSnackBar(context, '请先选择当前心情');
      return;
    }
    final entry = _quick[_selectedQuickIndex!];
    final mood = entry is Map ? entry['value']?.toString() : null;
    if (mood == null || mood.isEmpty) {
      showAppSnackBar(context, '心情数据无效');
      return;
    }
    setState(() {
      _loading = true;
      _result = null;
    });
    final auth = context.read<AuthProvider>();
    final raw = await auth.apiClient.recommendByMood(
      mood: mood,
      includeWardrobe: true,
    );
    if (!mounted) return;
    setState(() => _loading = false);
    if (raw.containsKey('error')) {
      showAppSnackBar(context, '获取失败：${userFacingApiError(raw['error'])}');
      return;
    }
    setState(() => _result = raw);
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    final base = context.read<AuthProvider>().apiClient.baseUrl;

    return AnalysisFeatureLayout(
      title: '情绪穿搭',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: palette.cardBg,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: palette.divider),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.favorite_rounded,
                          color: palette.primary, size: 18),
                      const SizedBox(width: 8),
                      Text(
                        '功能说明',
                        style: TextStyle(
                          color: palette.textTitle,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '系统会根据你的当前情绪，优先给出色彩与风格方向，再从衣橱里筛选更贴近该情绪语义的单品。',
                    style: TextStyle(
                      color: palette.textBody,
                      fontSize: 12,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _HintChip(
                        text: '先整理衣橱，推荐更准',
                        icon: Icons.checkroom_outlined,
                        color: Colors.blue,
                      ),
                      _HintChip(
                        text: '低落情绪更偏暖色',
                        icon: Icons.wb_sunny_outlined,
                        color: Colors.orange,
                      ),
                      _HintChip(
                        text: '可多次切换心情对比',
                        icon: Icons.compare_arrows_outlined,
                        color: Colors.green,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            Text(
              '告诉助手你此刻的心情，我们会结合色彩心理学给出风格、颜色建议，并尽量从你衣橱里挑出更契合的单品。',
              style: TextStyle(color: palette.textBody, height: 1.45),
            ),
            const SizedBox(height: 8),
            Text(
              '例如：心情不好时，会偏向暖色与轻松风格，帮助视觉上「暖一点」。',
              style: TextStyle(
                  fontSize: 13, color: palette.textBody.withValues(alpha: 0.9)),
            ),
            const SizedBox(height: 20),
            Text('此刻的心情',
                style: TextStyle(
                    fontWeight: FontWeight.w700, color: palette.textTitle)),
            const SizedBox(height: 10),
            if (_loadingQuick)
              const Center(
                  child: Padding(
                      padding: EdgeInsets.all(24),
                      child: CircularProgressIndicator()))
            else if (_quick.isEmpty)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.orange.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                  border:
                      Border.all(color: Colors.orange.withValues(alpha: 0.22)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline,
                        size: 16, color: Colors.orange),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '暂未获取到心情选项，请稍后重试。',
                        style: TextStyle(
                          fontSize: 12,
                          color: palette.textBody,
                          height: 1.35,
                        ),
                      ),
                    ),
                  ],
                ),
              )
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: List<Widget>.generate(_quick.length, (i) {
                  final e = _quick[i];
                  if (e is! Map) return const SizedBox.shrink();
                  final value = e['value']?.toString() ?? '';
                  final label = e['label']?.toString() ?? value;
                  final sel = _selectedQuickIndex == i;
                  return ChoiceChip(
                    label: Text(label, style: const TextStyle(fontSize: 13)),
                    selected: sel,
                    selectedColor: palette.chipSelectedBg,
                    labelStyle: TextStyle(
                      color:
                          sel ? palette.chipSelectedLabel : palette.textTitle,
                    ),
                    onSelected: (_) => setState(() => _selectedQuickIndex = i),
                  );
                }),
              ),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: _loading ? null : _go,
              icon: _loading
                  ? SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: palette.background),
                    )
                  : const Icon(Icons.favorite_outline),
              label: Text(_loading ? '生成中…' : '生成情绪穿搭建议'),
              style: FilledButton.styleFrom(
                backgroundColor: palette.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
            if (_result != null) ...[
              const SizedBox(height: 14),
              _MoodSummaryCard(result: _result!, palette: palette),
            ],
            if (_result != null) ...[
              const SizedBox(height: 24),
              _ResultCard(result: _result!, palette: palette, apiBase: base),
            ],
          ],
        ),
      ),
    );
  }
}

class _HintChip extends StatelessWidget {
  final String text;
  final IconData icon;
  final Color color;

  const _HintChip({
    required this.text,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              color: color.withValues(alpha: 0.95),
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _MoodSummaryCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final dynamic palette;

  const _MoodSummaryCard({
    required this.result,
    required this.palette,
  });

  @override
  Widget build(BuildContext context) {
    final moodCn = result['mood_cn']?.toString() ?? '未知';
    final styles = result['recommended_styles'];
    final occasions = result['recommended_occasions'];
    final items = result['matching_garments'];
    final styleCount = styles is List ? styles.length : 0;
    final occasionCount = occasions is List ? occasions.length : 0;
    final itemCount = items is List ? items.length : 0;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: palette.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.primary.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '结果摘要',
            style: TextStyle(
              color: palette.textTitle,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '当前情绪：$moodCn  |  推荐风格 $styleCount 项  |  场景 $occasionCount 项  |  匹配单品 $itemCount 件',
            style: TextStyle(
              color: palette.textBody,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          if (itemCount == 0) ...[
            const SizedBox(height: 6),
            Text(
              '当前没有检索到匹配衣橱单品，可先去衣橱补充几件常用基础款再重试。',
              style: TextStyle(
                color: palette.textBody,
                fontSize: 11,
                height: 1.35,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ResultCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final dynamic palette;
  final String apiBase;

  const _ResultCard({
    required this.result,
    required this.palette,
    required this.apiBase,
  });

  @override
  Widget build(BuildContext context) {
    final moodCn = result['mood_cn']?.toString() ?? '';
    final advice = result['advice']?.toString() ?? '';
    final colorExpl = result['color_explanation']?.toString() ?? '';
    final styles = result['recommended_styles'];
    final occasions = result['recommended_occasions'];
    final colors = result['recommended_colors'];
    final items = result['matching_garments'];

    return Card(
      color: palette.cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: palette.divider),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.psychology_outlined, color: palette.primary),
                const SizedBox(width: 8),
                Text(
                  '情绪：$moodCn',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                    color: palette.textTitle,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(advice,
                style: TextStyle(color: palette.textBody, height: 1.45)),
            const SizedBox(height: 10),
            Text(
              colorExpl,
              style: TextStyle(
                  fontSize: 13,
                  color: palette.textBody.withValues(alpha: 0.95)),
            ),
            if (styles is List && styles.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('推荐风格',
                  style: TextStyle(
                      fontWeight: FontWeight.w600, color: palette.textTitle)),
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: styles.map<Widget>((s) {
                  return Chip(
                    label: Text('$s', style: const TextStyle(fontSize: 12)),
                    backgroundColor: palette.chipUnselectedBg,
                    side: BorderSide(color: palette.divider),
                  );
                }).toList(),
              ),
            ],
            if (occasions is List && occasions.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('场景参考',
                  style: TextStyle(
                      fontWeight: FontWeight.w600, color: palette.textTitle)),
              const SizedBox(height: 4),
              Text(
                occasions.map((e) => e.toString()).join('、'),
                style: TextStyle(fontSize: 13, color: palette.textBody),
              ),
            ],
            if (colors is Map && colors.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('颜色倾向（权重）',
                  style: TextStyle(
                      fontWeight: FontWeight.w600, color: palette.textTitle)),
              const SizedBox(height: 4),
              Text(
                colors.entries
                    .map((e) =>
                        '${e.key} ${(e.value as num).toStringAsFixed(1)}')
                    .join(' · '),
                style: TextStyle(fontSize: 13, color: palette.textBody),
              ),
            ],
            if (items is List && items.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('衣橱中较匹配的单品',
                  style: TextStyle(
                      fontWeight: FontWeight.w600, color: palette.textTitle)),
              const SizedBox(height: 8),
              SizedBox(
                height: 112,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 10),
                  itemBuilder: (_, i) {
                    final g = items[i];
                    if (g is! Map) return const SizedBox.shrink();
                    final url = resolveGarmentImageUrl(
                        g['image_url']?.toString(), apiBase);
                    final cat = g['category']?.toString() ?? '';
                    final score = g['match_score'];
                    return SizedBox(
                      width: 88,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(12),
                              child: url != null
                                  ? PlatformImage(
                                      networkUrl: url, fit: BoxFit.cover)
                                  : ColoredBox(color: palette.divider),
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            cat,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 11, color: palette.textBody),
                          ),
                          if (score != null)
                            Text(
                              '匹配 ${(score is num ? score : double.tryParse('$score') ?? 0).toStringAsFixed(2)}',
                              style: TextStyle(
                                  fontSize: 10, color: palette.primary),
                            ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
