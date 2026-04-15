import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../services/api_client.dart';
import '../utils/app_snackbar.dart';
import '../utils/media_url.dart';
import 'platform_image.dart';

/// 从推荐结果 map 中收集 `garment_id`（用于反馈上报）。
List<String> extractOutfitGarmentIds(dynamic outfit) {
  if (outfit is! Map) return [];
  final raw = outfit['items'] ?? outfit['garments'];
  if (raw is! List) return [];
  final ids = <String>[];
  for (final g in raw) {
    if (g is Map && g['garment_id'] != null) {
      ids.add(g['garment_id'].toString());
    }
  }
  return ids;
}

/// Generic analysis result display widget.
/// Renders different card types: outfit, similarity, suitability.
class AnalysisResultDisplay extends StatelessWidget {
  final dynamic result;
  final String type; // 'outfit', 'similarity', 'suitability'
  /// 与 [AuthProvider.apiClient] 一致，用于拼接 `/uploads/` 图片地址。
  final String? apiBaseUrl;

  /// 保存到收藏（可异步）；用于调用 `POST /outfits/collections` 等。
  final Future<void> Function()? onSaveOutfit;
  final VoidCallback? onRetry;
  final bool saveOutfitLoading;

  /// 是否在每套搭配下显示「喜欢 / 采纳」并上报 `POST /feedback/events`
  final bool enableOutfitFeedback;
  final String outfitFeedbackSource;

  /// 0-based；与 [onSelectedOutfitIndexForSaveChanged] 同时使用时，表示「保存到收藏」针对第几套。
  final int? selectedOutfitIndexForSave;
  final ValueChanged<int>? onSelectedOutfitIndexForSaveChanged;

  const AnalysisResultDisplay({
    super.key,
    required this.result,
    required this.type,
    this.apiBaseUrl,
    this.onSaveOutfit,
    this.onRetry,
    this.enableOutfitFeedback = true,
    this.outfitFeedbackSource = 'analysis_outfit',
    this.saveOutfitLoading = false,
    this.selectedOutfitIndexForSave,
    this.onSelectedOutfitIndexForSaveChanged,
  });

  @override
  Widget build(BuildContext context) {
    final int saveIndexForHint = selectedOutfitIndexForSave ?? 0;

    if (result == null) {
      return _buildEmpty(context);
    }

    if (result is Map && result.containsKey('error')) {
      return _buildError(context, result['error'].toString());
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildHeader(context),
          const SizedBox(height: 16),
          ..._buildCards(context),
          if (onSaveOutfit != null) ...[
            const SizedBox(height: 24),
            if (onSelectedOutfitIndexForSaveChanged != null &&
                selectedOutfitIndexForSave != null) ...[
              Text(
                '点击某一「推荐」卡片以选中；保存到收藏将保存「推荐 #${saveIndexForHint + 1}」。',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      height: 1.35,
                    ),
              ),
              const SizedBox(height: 10),
            ],
            _buildSaveButton(context),
          ],
        ],
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.analytics_outlined,
            size: 64,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 16),
          Text(
            '暂无分析结果',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildError(BuildContext context, String error) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 16),
            Text(
              '分析失败',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              error,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('重试'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    String title;
    IconData icon;

    switch (type) {
      case 'outfit':
        title = '穿搭推荐结果';
        icon = Icons.style;
        break;
      case 'similarity':
        title = '相似度检测结果';
        icon = Icons.compare;
        break;
      case 'suitability':
        title = '适合度评分结果';
        icon = Icons.grade;
        break;
      default:
        title = '分析结果';
        icon = Icons.analytics;
    }

    return Row(
      children: [
        Icon(
          icon,
          color: Theme.of(context).colorScheme.primary,
        ),
        const SizedBox(width: 8),
        Text(
          title,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
        ),
      ],
    );
  }

  List<Widget> _buildCards(BuildContext context) {
    final List<Widget> cards = [];

    switch (type) {
      case 'outfit':
        if (result is Map) {
          // Backend v1 (legacy): { outfits: [...] }
          // Backend v2 (current): { outfit_cards: [...], target_garment: {...} }
          final raw = (result['outfit_cards'] ?? result['outfits']);
          final outfits = raw is List ? raw : <dynamic>[];
          final base = apiBaseUrl ?? ApiClient().baseUrl;
          final pickerOn = onSelectedOutfitIndexForSaveChanged != null;
          final sel = selectedOutfitIndexForSave ?? 0;
          for (var i = 0; i < outfits.length; i++) {
            cards.add(OutfitResultCard(
              outfit: outfits[i],
              index: i + 1,
              apiBaseUrl: base,
              enableFeedback: enableOutfitFeedback,
              feedbackSource: outfitFeedbackSource,
              saveTargetPickerEnabled: pickerOn,
              isSaveTarget: pickerOn && sel == i,
              onSelectAsSaveTarget: pickerOn
                  ? () => onSelectedOutfitIndexForSaveChanged!(i)
                  : null,
            ));
          }
          if (outfits.isEmpty &&
              (result.containsKey('outfit_cards') ||
                  result.containsKey('outfits'))) {
            cards.add(Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  '没有匹配到推荐结果。通常是因为衣橱里单品较少/为空：请先到「衣橱」上传几件服饰，再回来推荐。',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ));
          }
        }
        break;
      case 'similarity':
        if (result is Map) {
          // 兼容两类返回：
          // 1) 前端已归一化: { similar_items: [{ similarity, note, ... }] }
          // 2) 后端原始:   { similar_garments: [{ similarity_score, similarity_level, ... }] }
          final dynamic rawItems =
              result['similar_items'] ?? result['similar_garments'] ?? const [];
          final items = rawItems is List ? rawItems : <dynamic>[];
          for (final raw in items) {
            if (raw is Map) {
              final mapped = Map<String, dynamic>.from(raw);
              mapped['similarity'] =
                  mapped['similarity'] ?? mapped['similarity_score'] ?? 0.0;
              mapped['note'] =
                  mapped['note'] ?? mapped['similarity_level'] ?? '';
              cards.add(SimilarityResultCard(item: mapped));
            }
          }
        }
        break;
      case 'suitability':
        cards.add(SuitabilityResultCard(result: result));
        break;
    }

    if (cards.isEmpty) {
      cards.add(Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            '未找到相关结果',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
      ));
    }

    return cards;
  }

  Widget _buildSaveButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: saveOutfitLoading || onSaveOutfit == null
            ? null
            : () async {
                await onSaveOutfit!();
              },
        icon: saveOutfitLoading
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : const Icon(Icons.bookmark_add),
        label: Text(saveOutfitLoading ? '保存中…' : '保存到收藏'),
      ),
    );
  }
}

/// Card displaying a recommended outfit.
class OutfitResultCard extends StatefulWidget {
  final dynamic outfit;
  final int index;
  final String apiBaseUrl;
  final bool enableFeedback;
  final String feedbackSource;
  final bool saveTargetPickerEnabled;
  final bool isSaveTarget;
  final VoidCallback? onSelectAsSaveTarget;

  const OutfitResultCard({
    super.key,
    required this.outfit,
    required this.index,
    required this.apiBaseUrl,
    this.enableFeedback = false,
    this.feedbackSource = 'analysis_outfit',
    this.saveTargetPickerEnabled = false,
    this.isSaveTarget = false,
    this.onSelectAsSaveTarget,
  });

  @override
  State<OutfitResultCard> createState() => _OutfitResultCardState();
}

class _OutfitResultCardState extends State<OutfitResultCard> {
  bool _feedbackBusy = false;

  Future<void> _sendFeedback(BuildContext context, String eventType) async {
    if (_feedbackBusy) return;
    setState(() => _feedbackBusy = true);
    try {
      final auth = context.read<AuthProvider>();
      final ids = extractOutfitGarmentIds(widget.outfit);
      final scene = widget.outfit is Map
          ? (widget.outfit['scene'] ?? widget.outfit['recommended_scene'] ?? '')
              .toString()
              .trim()
          : '';
      final res = await auth.apiClient.submitFeedbackEvent(
        eventType: eventType,
        source: widget.feedbackSource,
        garmentId: ids.isNotEmpty ? ids.first : null,
        scene: scene.isNotEmpty ? scene : null,
        payload: {
          'outfit_index': widget.index,
          'garment_ids': ids,
        },
      );
      if (!context.mounted) return;
      if (res.containsKey('error')) {
        showAppSnackBar(
          context,
          '反馈未提交：${userFacingApiError(res['error'])}',
        );
      } else {
        showAppSnackBar(
          context,
          eventType == 'adopt' ? '已记录「采纳」' : '已记录「喜欢」',
        );
      }
    } finally {
      if (mounted) setState(() => _feedbackBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final outfit = widget.outfit;
    final dynamic rawScore = outfit is Map
        ? (outfit['overall_score'] ?? outfit['score'] ?? 0.0)
        : 0.0;
    final double score = rawScore is num ? rawScore.toDouble() : 0.0;

    // Backend may return either `garments` (legacy) or `items` (current).
    final dynamic rawItems =
        outfit is Map ? (outfit['items'] ?? outfit['garments']) : null;
    final List garments = rawItems is List ? rawItems : <dynamic>[];

    final scene = outfit is Map
        ? (outfit['scene'] ?? outfit['recommended_scene'] ?? '')
        : '';

    final cardBody = Card(
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: widget.saveTargetPickerEnabled && widget.isSaveTarget
            ? BorderSide(
                color: Theme.of(context).colorScheme.primary,
                width: 2,
              )
            : BorderSide.none,
      ),
      elevation: widget.saveTargetPickerEnabled && widget.isSaveTarget ? 3 : 1,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '推荐 #${widget.index}',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color:
                              Theme.of(context).colorScheme.onPrimaryContainer,
                          fontWeight: FontWeight.bold,
                        ),
                  ),
                ),
                if (widget.saveTargetPickerEnabled && widget.isSaveTarget) ...[
                  const SizedBox(width: 8),
                  Icon(
                    Icons.bookmark_added_outlined,
                    size: 18,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    '将保存此套',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ],
                const Spacer(),
                _buildScoreChip(context, score),
              ],
            ),
            if (scene.toString().isNotEmpty) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(
                    Icons.location_on,
                    size: 16,
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    scene.toString(),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ],
            if (garments.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                '包含单品:',
                style: Theme.of(context).textTheme.labelMedium,
              ),
              const SizedBox(height: 8),
              Builder(builder: (context) {
                return Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: garments.map((g) {
                    final rawUrl = (g is Map)
                        ? (g['image_url']?.toString() ?? '').trim()
                        : '';
                    final rawPath = (g is Map)
                        ? (g['image_path']?.toString() ?? '').trim()
                        : '';
                    final url = resolveGarmentImageUrl(
                      rawUrl.isNotEmpty ? rawUrl : rawPath,
                      widget.apiBaseUrl,
                    );
                    final label = (g is Map)
                        ? (g['category']?.toString() ??
                            g['name']?.toString() ??
                            g['role']?.toString() ??
                            '未知')
                        : '未知';
                    return Container(
                      width: 92,
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: Theme.of(context)
                              .colorScheme
                              .outlineVariant
                              .withOpacity(0.6),
                        ),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: PlatformImage(
                              networkUrl: url,
                              width: 80,
                              height: 80,
                              fit: BoxFit.cover,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.labelSmall,
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                );
              }),
            ],
            if (widget.enableFeedback) ...[
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _feedbackBusy
                          ? null
                          : () => _sendFeedback(context, 'like'),
                      icon: _feedbackBusy
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.favorite_border, size: 18),
                      label: const Text('喜欢'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _feedbackBusy
                          ? null
                          : () => _sendFeedback(context, 'adopt'),
                      icon: const Icon(Icons.check_circle_outline, size: 18),
                      label: const Text('采纳'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '记录后将用于推荐优化与数据统计',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.outline,
                    ),
              ),
            ],
          ],
        ),
      ),
    );

    if (widget.saveTargetPickerEnabled && widget.onSelectAsSaveTarget != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.onSelectAsSaveTarget,
            borderRadius: BorderRadius.circular(12),
            child: cardBody,
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: cardBody,
    );
  }

  Widget _buildScoreChip(BuildContext context, double score) {
    Color color;
    if (score >= 0.8) {
      color = Colors.green;
    } else if (score >= 0.6) {
      color = Colors.orange;
    } else {
      color = Colors.red;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Text(
        '${(score * 100).toStringAsFixed(0)}%',
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: color,
              fontWeight: FontWeight.bold,
            ),
      ),
    );
  }
}

/// Card displaying a similarity detection result.
class SimilarityResultCard extends StatelessWidget {
  final dynamic item;

  const SimilarityResultCard({
    super.key,
    required this.item,
  });

  @override
  Widget build(BuildContext context) {
    final similarityRaw = item['similarity'] ?? item['score'] ?? 0.0;
    final similarity = similarityRaw is num ? similarityRaw.toDouble() : 0.0;
    final category = item['category']?.toString() ?? '未知';
    final note = item['note']?.toString() ?? '';

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    category,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (note.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      note,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color:
                                Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                ],
              ),
            ),
            _buildSimilarityIndicator(context, similarity),
          ],
        ),
      ),
    );
  }

  Widget _buildSimilarityIndicator(BuildContext context, double similarity) {
    Color color;
    String label;
    if (similarity >= 0.8) {
      color = Colors.red;
      label = '高度相似';
    } else if (similarity >= 0.5) {
      color = Colors.orange;
      label = '中度相似';
    } else {
      color = Colors.green;
      label = '略有相似';
    }

    return Column(
      children: [
        SizedBox(
          width: 48,
          height: 48,
          child: Stack(
            children: [
              CircularProgressIndicator(
                value: similarity,
                strokeWidth: 4,
                backgroundColor: color.withOpacity(0.2),
                valueColor: AlwaysStoppedAnimation(color),
              ),
              Center(
                child: Text(
                  '${(similarity * 100).toStringAsFixed(0)}%',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: color,
              ),
        ),
      ],
    );
  }
}

/// Card displaying a suitability analysis result.
class SuitabilityResultCard extends StatelessWidget {
  final dynamic result;

  const SuitabilityResultCard({
    super.key,
    required this.result,
  });

  @override
  Widget build(BuildContext context) {
    final overallRaw = result['overall_score'] ??
        result['suitability'] ??
        result['suitability_score'] ??
        0.0;
    final overall = _toUnitScore(overallRaw);
    final scene = result['scene'] ?? result['recommended_scene'] ?? '';
    final sceneScore = _toUnitScore(result['scene_score'] ?? 0.0);
    final bodyScore = _toUnitScore(
      result['body_score'] ??
          result['body_shape_score'] ??
          result['fit_score'] ??
          0.0,
    );
    final styleScore = _toUnitScore(result['style_score'] ?? 0.0);

    final exp = result['explanation'];
    final expMap = exp is Map ? exp : null;
    final sceneReason = (result['scene_match_reason'] ??
            expMap?['scene'] ??
            result['scene_reason'] ??
            '')
        .toString();
    final bodyReason =
        (result['body_fit_reason'] ?? expMap?['body'] ?? '').toString();
    final styleReason =
        (result['style_coordination_reason'] ?? expMap?['style'] ?? '')
            .toString();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  '综合评分',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Spacer(),
                _buildOverallScore(context, overall),
              ],
            ),
            if (scene.toString().isNotEmpty) ...[
              const SizedBox(height: 8),
              Chip(
                avatar: const Icon(Icons.location_on, size: 16),
                label: Text(scene.toString()),
                visualDensity: VisualDensity.compact,
              ),
            ],
            const SizedBox(height: 16),
            const Divider(),
            const SizedBox(height: 16),
            _buildScoreRow(context, '场景匹配', sceneScore, sceneReason),
            const SizedBox(height: 12),
            _buildScoreRow(context, '体型适配', bodyScore, bodyReason),
            const SizedBox(height: 12),
            _buildScoreRow(context, '风格协调', styleScore, styleReason),
          ],
        ),
      ),
    );
  }

  double _toUnitScore(dynamic v) {
    if (v is num) {
      final x = v.toDouble();
      if (x > 1.0) return (x / 100.0).clamp(0.0, 1.0);
      return x.clamp(0.0, 1.0);
    }
    return 0.0;
  }

  Widget _buildOverallScore(BuildContext context, double score) {
    Color color;
    if (score >= 0.8) {
      color = Colors.green;
    } else if (score >= 0.6) {
      color = Colors.orange;
    } else {
      color = Colors.red;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star, color: color, size: 20),
          const SizedBox(width: 4),
          Text(
            '${(score * 100).toStringAsFixed(0)}%',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: color,
                  fontWeight: FontWeight.bold,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreRow(
      BuildContext context, String label, double score, String reason) {
    final r = reason.trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SizedBox(
              width: 80,
              child: Text(
                label,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: score,
                  minHeight: 8,
                  backgroundColor:
                      Theme.of(context).colorScheme.surfaceContainerHighest,
                ),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 48,
              child: Text(
                '${(score * 100).toStringAsFixed(0)}%',
                textAlign: TextAlign.end,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
            ),
          ],
        ),
        if (r.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            r,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  height: 1.35,
                ),
          ),
        ],
      ],
    );
  }
}
