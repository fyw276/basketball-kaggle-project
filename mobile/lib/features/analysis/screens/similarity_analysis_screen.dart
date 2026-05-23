import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/platform_image.dart';
import '../../../core/widgets/wardrobe_picker_sheet.dart';

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

  /// 从衣橱选择时记录 garment_id / image_url（与 _images 互斥）。
  String? _wardrobeGarmentId;
  String? _wardrobeImageUrl;

  static const _cacheKey = 'similarity_analysis';

  @override
  void initState() {
    super.initState();
    FeatureLocalStore.loadJson(_cacheKey).then((m) {
      if (m != null && mounted) {
        // Normalize cached data to ensure image_url is present (old caches may lack it)
        setState(() => _result = _normalizeApiResult(m));
      }
    });
  }

  /// 将后端 SimilarityAnalysisResponse 转为界面使用的结构
  Map<String, dynamic> _normalizeApiResult(Map<String, dynamic> raw) {
    // Handle raw API response (has similar_garments)
    if (raw.containsKey('similar_garments') &&
        !raw.containsKey('similar_items')) {
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
    // Handle already-normalized data (from cache) — ensure image_url is preserved
    if (raw.containsKey('similar_items')) {
      final list = raw['similar_items'];
      if (list is List) {
        final fixed = <Map<String, dynamic>>[];
        for (final e in list) {
          if (e is! Map) continue;
          final m = Map<String, dynamic>.from(e);
          // Ensure image_url is always present as a string key
          m.putIfAbsent('image_url', () => null);
          fixed.add(m);
        }
        return {
          'tip': raw['tip']?.toString() ?? '',
          'similar_items': fixed,
          'avoid_duplicates': raw['avoid_duplicates'] == true,
        };
      }
    }
    return raw;
  }

  Future<void> _analyze() async {
    if (_images.isEmpty && _wardrobeGarmentId == null) return;
    // Clear old cache to ensure fresh data
    await FeatureLocalStore.clear(_cacheKey);
    setState(() {
      _loading = true;
      _result = null;
    });

    final auth = context.read<AuthProvider>();
    try {
      final raw = await auth.apiClient.analyzeSimilarity(
        imageFile: _wardrobeGarmentId == null ? _images.first : null,
        garmentId: _wardrobeGarmentId,
        imageUrl: _wardrobeGarmentId == null ? null : _wardrobeImageUrl,
      );
      if (!mounted) return;

      if (raw.containsKey('error')) {
        showAppSnackBar(context, '检测失败：${userFacingApiError(raw['error'])}');
        setState(() => _loading = false);
        return;
      }

      // ignore: avoid_print
      print('[Similarity] raw API response: $raw');
      final normalized = _normalizeApiResult(Map<String, dynamic>.from(raw));
      // ignore: avoid_print
      print(
          '[Similarity] normalized similar_items count: ${(normalized['similar_items'] as List?)?.length}');
      for (final item in (normalized['similar_items'] as List? ?? [])) {
        // ignore: avoid_print
        print('[Similarity] item image_url: ${item['image_url']}');
      }
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
    final apiBase = context.read<AuthProvider>().apiClient.baseUrl;
    return AnalysisFeatureLayout(
      title: '相似衣物检测',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    palette.surface.withValues(alpha: 0.96),
                    palette.primary.withValues(alpha: 0.06),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
                border:
                    Border.all(color: palette.divider.withValues(alpha: 0.9)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 12,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.auto_graph_outlined,
                          color: palette.primary, size: 18),
                      const SizedBox(width: 8),
                      Text(
                        '功能说明',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: palette.textTitle,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '上传一张清晰的单品图，系统会在衣橱中查找相似单品，帮助你避免重复购买。',
                    style: TextStyle(
                      fontSize: 12,
                      color: palette.textBody,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: const [
                      _SimilarityHintChip(
                          label: '清晰单品图',
                          icon: Icons.photo_outlined,
                          color: Colors.blue),
                      _SimilarityHintChip(
                          label: '主体完整',
                          icon: Icons.crop_free_outlined,
                          color: Colors.green),
                      _SimilarityHintChip(
                          label: '避免拼图',
                          icon: Icons.grid_off_outlined,
                          color: Colors.orange),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            ImagePickerSection(
              images: _images,
              onImagesChanged: (list) => setState(() {
                _images = list;
                // 用户手动上传图片时清除衣橱选择
                if (list.isNotEmpty) {
                  _wardrobeGarmentId = null;
                  _wardrobeImageUrl = null;
                }
              }),
              maxImages: 1,
              hintText: '上传服装图片',
              allowMultiple: false,
              onWardrobeTap: () async {
                final picked = await showWardrobePicker(context);
                if (picked != null && picked.isNotEmpty) {
                  setState(() {
                    _images = [];
                    _wardrobeGarmentId = picked.first.garmentId;
                    _wardrobeImageUrl = picked.first.imageUrl;
                  });
                }
              },
            ),
            if (_wardrobeGarmentId != null && _wardrobeImageUrl != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Container(
                  height: 100,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: palette.divider),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: PlatformImage(
                          networkUrl: resolveGarmentImageUrl(
                                  _wardrobeImageUrl, apiBase) ??
                              _wardrobeImageUrl!,
                          fit: BoxFit.cover,
                          placeholder: Center(
                            child: Icon(Icons.checkroom,
                                color: palette.primary, size: 32),
                          ),
                          errorWidget: Center(
                            child: Icon(Icons.broken_image,
                                color: palette.textBody, size: 32),
                          ),
                        ),
                      ),
                      Positioned(
                        left: 8,
                        bottom: 8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.55),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            '已从衣橱选择',
                            style: TextStyle(color: Colors.white, fontSize: 11),
                          ),
                        ),
                      ),
                      Positioned(
                        top: 4,
                        right: 4,
                        child: GestureDetector(
                          onTap: () => setState(() {
                            _wardrobeGarmentId = null;
                            _wardrobeImageUrl = null;
                          }),
                          child: Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.45),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.close,
                                size: 16, color: Colors.white),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              )
            else if (_wardrobeGarmentId != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Row(
                  children: [
                    Icon(Icons.checkroom,
                        size: 16, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 6),
                    Text('已从衣橱选择',
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.primary,
                            fontSize: 13)),
                    const Spacer(),
                    TextButton(
                      onPressed: () => setState(() {
                        _wardrobeGarmentId = null;
                        _wardrobeImageUrl = null;
                      }),
                      child: const Text('清除'),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed:
                    ((_images.isNotEmpty || _wardrobeGarmentId != null) &&
                            !_loading)
                        ? _analyze
                        : null,
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
                  _loading ? '生成中…' : '生成检测结果',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            const SizedBox(height: 24),
            if (_result != null) ...[
              if ((_result!['avoid_duplicates'] == true) ||
                  ((_result!['similar_items'] as List?)?.isNotEmpty ??
                      false)) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: (_result!['avoid_duplicates'] == true
                            ? Colors.redAccent
                            : palette.primary)
                        .withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: (_result!['avoid_duplicates'] == true
                              ? Colors.redAccent
                              : palette.primary)
                          .withValues(alpha: 0.25),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _result!['avoid_duplicates'] == true
                            ? Icons.warning_amber_rounded
                            : Icons.info_outline,
                        color: _result!['avoid_duplicates'] == true
                            ? Colors.redAccent
                            : palette.primary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _result!['avoid_duplicates'] == true
                              ? '检测到较高重复购买风险，建议先看看下面的相似单品。'
                              : '已找到相似单品，可对比后决定是否购买。',
                          style: TextStyle(
                            fontSize: 12,
                            color: palette.textBody,
                            height: 1.35,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],
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
                final rawUrl = row['image_url']?.toString();
                final imageUrl = resolveGarmentImageUrl(rawUrl, apiBase);
                // ignore: avoid_print
                print(
                    '[Similarity] rawUrl=$rawUrl, resolved=$imageUrl, apiBase=$apiBase');
                return Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: BorderSide(color: palette.divider),
                  ),
                  child: ListTile(
                    leading: SizedBox(
                      width: 56,
                      height: 56,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            if (imageUrl != null)
                              PlatformImage(
                                networkUrl: imageUrl,
                                fit: BoxFit.cover,
                              )
                            else
                              ColoredBox(
                                color: palette.primary.withValues(alpha: 0.08),
                              ),
                            Positioned(
                              right: 2,
                              bottom: 2,
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 4, vertical: 2),
                                decoration: BoxDecoration(
                                  color: color.withValues(alpha: 0.85),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  '${(sim * 100).toInt()}%',
                                  style: const TextStyle(
                                    fontSize: 10,
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ),
                          ],
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

class _SimilarityHintChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;

  const _SimilarityHintChip({
    required this.label,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: Icon(icon, size: 16, color: color),
      label: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: color.withValues(alpha: 0.92),
        ),
      ),
      backgroundColor: color.withValues(alpha: 0.08),
      side: BorderSide(color: color.withValues(alpha: 0.18)),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(999),
      ),
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
    );
  }
}
