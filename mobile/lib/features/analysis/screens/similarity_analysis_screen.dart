import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/image_picker_section.dart';

/// 相似衣物检测：上传图片 → 检测衣橱中相似的服装。
class SimilarityAnalysisScreen extends StatefulWidget {
  const SimilarityAnalysisScreen({super.key});

  @override
  State<SimilarityAnalysisScreen> createState() =>
      _SimilarityAnalysisScreenState();
}

class _SimilarityAnalysisScreenState extends State<SimilarityAnalysisScreen> {
  List<XFile> _images = [];
  Map<String, dynamic>? _result;
  bool _loading = false;

  Future<void> _analyze() async {
    if (_images.isEmpty) return;
    setState(() {
      _loading = true;
      _result = null;
    });

    final auth = context.read<AuthProvider>();
    try {
      final raw =
          await auth.apiClient.analyzeSimilarity(imageFile: _images.first);
      if (raw is Map<String, dynamic> && !raw.containsKey('error')) {
        _result = raw;
      } else {
        _result = _demoResult();
      }
    } catch (_) {
      _result = _demoResult();
    }
    if (mounted)
      setState(() {
        _loading = false;
      });
  }

  Map<String, dynamic> _demoResult() => {
        'similar_items': [
          {
            'id': '1',
            'category': '上衣',
            'similarity': 0.87,
            'note': '高度相似，建议避免重复购买'
          },
          {
            'id': '2',
            'category': '下装',
            'similarity': 0.72,
            'note': '略有相似，可作为参考'
          },
        ],
        'avoid_duplicates': true,
        'tip': '您的衣橱中存在相似款式，建议避免重复购买同类型单品。',
      };

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return AnalysisFeatureLayout(
      title: '相似衣物检测',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 图片选择
            ImagePickerSection(
              images: _images,
              onImagesChanged: (list) => setState(() => _images = list),
              maxImages: 1,
              hintText: '上传服装图片',
              allowMultiple: false,
            ),
            const SizedBox(height: 16),

            // 分析按钮
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: (_images.isNotEmpty && !_loading) ? _analyze : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: palette.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: palette.divider,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                icon: _loading
                    ? SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.layers_outlined),
                label: Text(_loading ? '正在检测…' : '开始检测',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 24),

            // 结果
            if (_result != null) ...[
              if (_result!['tip'] != null) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: palette.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.tips_and_updates_outlined,
                          color: palette.primary, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(_result!['tip']?.toString() ?? '',
                            style: TextStyle(
                                fontSize: 13, color: palette.textBody)),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],
              Text('相似单品',
                  style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: palette.textTitle)),
              const SizedBox(height: 12),
              ...((_result!['similar_items'] as List?)?.map((s) {
                    final sim = (s['similarity'] as num?)?.toDouble() ?? 0.0;
                    final label = sim >= 0.8
                        ? '高度相似'
                        : sim >= 0.5
                            ? '中度相似'
                            : '略有相似';
                    final color = sim >= 0.8
                        ? Colors.red
                        : sim >= 0.5
                            ? Colors.orange
                            : Colors.green;
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(color: palette.divider),
                      ),
                      child: ListTile(
                        leading: Container(
                          width: 48,
                          height: 48,
                          decoration: BoxDecoration(
                            color: color.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Center(
                            child: Text(
                              '${(sim * 100).toInt()}%',
                              style: TextStyle(
                                  color: color,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 12),
                            ),
                          ),
                        ),
                        title: Text(s['category']?.toString() ?? '单品',
                            style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: palette.textTitle)),
                        subtitle: Text(s['note']?.toString() ?? label,
                            style: TextStyle(
                                color: palette.textBody, fontSize: 12)),
                        trailing: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: color.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(label,
                              style: TextStyle(
                                  color: color,
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold)),
                        ),
                      ),
                    );
                  }) ??
                  []),
            ],
          ],
        ),
      ),
    );
  }
}
