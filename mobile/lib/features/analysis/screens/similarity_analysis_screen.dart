import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/image_picker_section.dart';

/// 相似衣物检测：与后端 `/analysis/similarity` 字段对齐。
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

  static const _cacheKey = 'similarity_analysis';

  @override
  void initState() {
    super.initState();
    FeatureLocalStore.loadJson(_cacheKey).then((m) {
      if (m != null && mounted) setState(() => _result = m);
    });
  }

  /// 将后端 SimilarityAnalysisResponse 转为界面使用的结构
  Map<String, dynamic> _normalizeApiResult(Map<String, dynamic> raw) {
    if (raw.containsKey('similar_items')) {
      return raw;
    }
    final list = raw['similar_garments'];
    final similarItems = <Map<String, dynamic>>[];
    if (list is List) {
      for (final e in list) {
        if (e is! Map) continue;
        final m = Map<String, dynamic>.from(e);
        similarItems.add({
          'category': m['category']?.toString() ?? '—',
          'similarity': (m['similarity_score'] as num?)?.toDouble() ?? 0.0,
          'note': m['similarity_level']?.toString() ?? '',
          'image_url': m['image_url']?.toString(),
        });
      }
    }
    return {
      'tip': raw['recommendation']?.toString() ?? '',
      'similar_items': similarItems,
      'avoid_duplicates': raw['has_duplicate_warning'] == true,
    };
  }

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
      if (!mounted) return;

      if (raw.containsKey('error')) {
        showAppSnackBar(context, '检测失败：${userFacingApiError(raw['error'])}');
        setState(() => _loading = false);
        return;
      }

      final normalized = _normalizeApiResult(Map<String, dynamic>.from(raw));
      setState(() {
        _result = normalized;
        _loading = false;
      });
      FeatureLocalStore.saveJson(_cacheKey, normalized);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '请求异常：${userFacingApiError(e)}');
        setState(() => _loading = false);
      }
    }
  }

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
            ImagePickerSection(
              images: _images,
              onImagesChanged: (list) => setState(() => _images = list),
              maxImages: 1,
              hintText: '上传服装图片',
              allowMultiple: false,
            ),
            const SizedBox(height: 16),
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
                      borderRadius: BorderRadius.circular(18)),
                ),
                icon: _loading
                    ? SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.layers_outlined),
                label: Text(
                  _loading ? '正在检测…' : '开始检测',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            const SizedBox(height: 24),
            if (_result != null) ...[
              if ((_result!['tip']?.toString() ?? '').isNotEmpty) ...[
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
                        child: Text(
                          _result!['tip']?.toString() ?? '',
                          style:
                              TextStyle(fontSize: 13, color: palette.textBody),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],
              Text(
                '相似单品',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: palette.textTitle),
              ),
              const SizedBox(height: 12),
              ...(((_result!['similar_items'] as List?) ?? []).map<Widget>((s) {
                final row = Map<String, dynamic>.from(s as Map);
                final sim = (row['similarity'] as num?)?.toDouble() ?? 0.0;
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
                    title: Text(
                      row['category']?.toString() ?? '单品',
                      style: TextStyle(
                          fontWeight: FontWeight.bold,
                          color: palette.textTitle),
                    ),
                    subtitle: Text(
                      row['note']?.toString() ?? label,
                      style: TextStyle(color: palette.textBody, fontSize: 12),
                    ),
                    trailing: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        label,
                        style: TextStyle(
                            color: color,
                            fontSize: 11,
                            fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                );
              }).toList()),
            ],
          ],
        ),
      ),
    );
  }
}
