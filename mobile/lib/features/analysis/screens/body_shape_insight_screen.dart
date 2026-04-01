import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../profile/screens/personal_settings_screen.dart';

/// 体型感知：结合个人资料给出可执行的穿搭方向，并引导完善资料。
class BodyShapeInsightScreen extends StatefulWidget {
  const BodyShapeInsightScreen({super.key});

  @override
  State<BodyShapeInsightScreen> createState() => _BodyShapeInsightScreenState();
}

class _BodyShapeInsightScreenState extends State<BodyShapeInsightScreen> {
  Future<Map<String, dynamic>>? _future;

  static const _cacheKey = 'body_shape';

  /// 与后端 `outfit_recommender_3d.BODY_TYPE_IDEAL_FITS` 对齐的展示文案
  static const Map<String, List<String>> _idealFitHints = {
    '偏瘦': ['宽松', 'oversized', '标准版型'],
    '倒三角': ['宽松上衣', 'oversized'],
    '梨形': ['宽松', 'oversized', '标准'],
    '矩形': ['修身', '标准', '宽松'],
    '沙漏': ['修身', '标准'],
    '微胖': ['宽松', 'oversized', '标准'],
  };

  static const Map<String, String> _bodyCopy = {
    '偏瘦': '可通过略宽松或叠穿增加体积感，避免过度紧身显得单薄。',
    '倒三角': '上半身宜略宽松或深色简化，下半身可强调线条平衡肩宽。',
    '梨形': '上半身可适当提亮或增加细节，下半身优选垂坠宽松的下装。',
    '矩形': '可用腰线、层次与修身单品塑造曲线。',
    '沙漏': '突出腰线与合身剪裁，整体比例优势明显。',
    '微胖': '优选垂坠面料与适度宽松，避免过紧剪裁突出赘肉。',
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _future = _loadProfile();
      });
    });
  }

  Future<Map<String, dynamic>> _loadProfile() async {
    final cached = await FeatureLocalStore.loadJson(_cacheKey);
    if (!mounted) return cached ?? <String, dynamic>{};
    final auth = context.read<AuthProvider>();
    try {
      final live = await auth.apiClient.getProfile();
      if (!live.containsKey('error')) {
        await FeatureLocalStore.saveJson(_cacheKey, live);
        return live;
      }
    } catch (_) {}
    return cached ?? <String, dynamic>{};
  }

  void _openSettings() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const PersonalSettingsScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return AnalysisFeatureLayout(
      title: '体型感知',
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snap) {
          if (_future == null || snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final data = snap.data;
          final body = data != null && !data.containsKey('error')
              ? data
              : <String, dynamic>{};
          final height = body['height'];
          final bt = body['body_type']?.toString() ?? '';
          final avoid = body['avoid_body_parts'];
          final styles = body['style_preference'];
          final ideal = _idealFitHints[bt];
          final intro = _bodyCopy[bt] ?? '完善体型与偏好后，推荐与适合度分析会结合身形给出更贴合的搭配建议。';

          String avoidStr = '';
          if (avoid is List && avoid.isNotEmpty) {
            avoidStr = avoid.map((e) => e.toString()).join('、');
          }

          String styleStr = '';
          if (styles is List && styles.isNotEmpty) {
            styleStr = styles.map((e) => e.toString()).join('、');
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '结合您在「设置」中的身高、体型与偏好，下面给出可执行的穿搭方向（与推荐引擎中的体型规则一致）。',
                  style: TextStyle(color: palette.textBody, height: 1.45),
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading:
                              Icon(Icons.straighten, color: palette.primary),
                          title: const Text('身高'),
                          trailing: Text(
                            height != null ? '$height cm' : '未填写',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: palette.textTitle,
                            ),
                          ),
                        ),
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: Icon(Icons.accessibility_new,
                              color: palette.primary),
                          title: const Text('体型'),
                          trailing: Text(
                            bt.isNotEmpty ? bt : '未填写',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: palette.textTitle,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  '体型解读',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: palette.textTitle,
                  ),
                ),
                const SizedBox(height: 8),
                Text(intro,
                    style: TextStyle(color: palette.textBody, height: 1.45)),
                if (ideal != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    '推荐版型倾向',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: palette.textTitle,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: ideal
                        .map(
                          (s) => Chip(
                            label:
                                Text(s, style: const TextStyle(fontSize: 13)),
                            backgroundColor: palette.chipUnselectedBg,
                            side: BorderSide(color: palette.divider),
                          ),
                        )
                        .toList(),
                  ),
                ],
                if (avoidStr.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    '希望修饰的部位',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: palette.textTitle,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(avoidStr,
                      style: TextStyle(color: palette.textBody, height: 1.45)),
                ],
                if (styleStr.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    '风格偏好',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: palette.textTitle,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(styleStr,
                      style: TextStyle(color: palette.textBody, height: 1.45)),
                ],
                const SizedBox(height: 20),
                Text(
                  '说明：穿搭推荐与适合度分析会读取上述资料；若资料为空，将仅根据图片与衣橱做通用推荐。',
                  style: TextStyle(
                      fontSize: 13,
                      color: palette.textBody.withValues(alpha: 0.85)),
                ),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _openSettings,
                  icon: const Icon(Icons.edit_outlined, size: 20),
                  label: const Text('去个人设置完善资料'),
                  style: FilledButton.styleFrom(
                    backgroundColor: palette.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
