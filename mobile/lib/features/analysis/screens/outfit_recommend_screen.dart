import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart';
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/platform_image.dart';
import '../../../core/widgets/wardrobe_picker_sheet.dart';

/// Outfit recommendation screen.
class OutfitRecommendScreen extends StatefulWidget {
  const OutfitRecommendScreen({super.key});

  @override
  State<OutfitRecommendScreen> createState() => _OutfitRecommendScreenState();
}

class _OutfitRecommendScreenState extends State<OutfitRecommendScreen> {
  final List<XFile> _images = [];
  Map<String, dynamic>? _result;
  bool _isLoading = false;
  bool _saveBusy = false;

  /// 从衣橱选择的衣物 ID 列表（与 _images 互斥）。
  List<String> _wardrobeGarmentIds = [];

  /// 从衣橱选择的衣物图片 URL 列表（与 _wardrobeGarmentIds 对应）。
  List<String> _wardrobeImageUrls = [];

  /// 保存到收藏时选中的搭配（0-based，对应 `outfit_cards` 下标）
  int _selectedOutfitIndexForSave = 0;
  String? _selectedScene;

  static const _cacheKey = 'outfit_recommend_v2';

  @override
  void initState() {
    super.initState();
    // 不在此恢复缓存：否则会一直显示「上一次的推荐」，换图后也容易误以为没更新。
  }

  final List<String> _scenes = [
    '日常休闲',
    '职场商务',
    '约会聚会',
    '运动健身',
    '正式场合',
  ];

  Future<void> _analyze() async {
    if (_images.isEmpty && _wardrobeGarmentIds.isEmpty) {
      showAppSnackBar(context, '请先选择图片');
      return;
    }

    final authProvider = context.read<AuthProvider>();
    final ge = context.read<ThemeProvider>().genderExpression;

    setState(() {
      _isLoading = true;
      _result = null;
    });
    await FeatureLocalStore.clear(_cacheKey);
    if (!mounted) return;

    try {
      final result = await authProvider.apiClient.recommendOutfits(
        imageFiles:
            _wardrobeGarmentIds.isEmpty ? List<dynamic>.from(_images) : null,
        garmentIds: _wardrobeGarmentIds.isNotEmpty ? _wardrobeGarmentIds : null,
        numOutfits: 5,
        genderExpression: ge,
        scene: _selectedScene,
      );

      if (result.containsKey('error')) {
        if (mounted) {
          showAppSnackBar(
            context,
            '推荐暂不可用：${userFacingApiError(result['error'])}',
          );
        }
        setState(() {
          _isLoading = false;
          _result = null;
        });
        return;
      }

      setState(() {
        _result = result;
        _isLoading = false;
        _selectedOutfitIndexForSave = 0;
      });
      FeatureLocalStore.saveJson(_cacheKey, result);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '网络异常：${userFacingApiError(e)}');
      }
      setState(() {
        _isLoading = false;
        _result = null;
      });
    }
  }

  /// 将**当前选中**的那一套推荐保存到套装收藏，并自动上报 `adopt` 反馈（与后端飞轮/重排对齐）。
  Future<void> _saveSelectedOutfitToCollection() async {
    final result = _result;
    if (result == null || !mounted) return;
    final raw = result['outfit_cards'] ?? result['outfits'];
    if (raw is! List || raw.isEmpty) {
      showAppSnackBar(context, '没有可保存的搭配');
      return;
    }
    final idx = _selectedOutfitIndexForSave.clamp(0, raw.length - 1);
    final selected = raw[idx];
    final ids = extractOutfitGarmentIds(selected);
    if (ids.isEmpty) {
      showAppSnackBar(context, '缺少单品ID，请确认衣橱有单品且已生成推荐');
      return;
    }
    var sceneStr = '休闲日常';
    if (selected is Map) {
      final s = selected['scene'] ?? selected['recommended_scene'];
      if (s != null && s.toString().trim().isNotEmpty) {
        sceneStr = s.toString().trim();
      } else if (_selectedScene != null && _selectedScene!.trim().isNotEmpty) {
        sceneStr = _selectedScene!.trim();
      }
    }
    var name = '场景推荐 · $sceneStr';
    if (name.length > 50) name = name.substring(0, 50);
    if (sceneStr.length > 50) sceneStr = sceneStr.substring(0, 50);

    setState(() => _saveBusy = true);
    try {
      final auth = context.read<AuthProvider>();
      final saveRes = await auth.apiClient.saveOutfitCollection(
        name: name,
        scene: sceneStr,
        garmentIds: ids,
      );
      if (!mounted) return;
      if (saveRes.containsKey('error')) {
        showAppSnackBar(
          context,
          '保存失败：${userFacingApiError(saveRes['error'])}',
        );
        return;
      }
      final cid = saveRes['collection_id']?.toString();
      final fbRes = await auth.apiClient.submitFeedbackEvent(
        eventType: 'adopt',
        source: 'analysis_outfit',
        collectionId: cid,
        garmentId: ids.first,
        scene: sceneStr,
        payload: {
          'garment_ids': ids,
          'from_save_to_collection': true,
          'outfit_index': idx + 1,
        },
      );
      if (!mounted) return;
      if (fbRes.containsKey('error')) {
        showAppSnackBar(
          context,
          '收藏已保存，反馈同步失败：${userFacingApiError(fbRes['error'])}',
        );
      } else {
        showAppSnackBar(context, '已保存到收藏');
      }
    } finally {
      if (mounted) setState(() => _saveBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return AnalysisFeatureLayout(
      title: '穿搭推荐',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
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
                      Icon(Icons.auto_awesome_outlined,
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
                    '支持最多 5 张图片合并推荐。建议上传同一风格或同一套穿搭的单品图，系统会结合衣橱与性别表达指数给出更合适的搭配方案。',
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
                      _RecommendHintChip(
                        label: '同风格更准',
                        icon: Icons.style_outlined,
                        color: Colors.blue,
                      ),
                      _RecommendHintChip(
                        label: '最多 5 张',
                        icon: Icons.photo_library_outlined,
                        color: Colors.green,
                      ),
                      _RecommendHintChip(
                        label: '可选场景',
                        icon: Icons.location_on_outlined,
                        color: Colors.orange,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // Scene selection
            Text(
              '选择场景',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(color: palette.textTitle),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _scenes.map((scene) {
                final isSelected = _selectedScene == scene;
                return ChoiceChip(
                  label: Text(scene),
                  selected: isSelected,
                  onSelected: (selected) {
                    setState(() {
                      _selectedScene = selected ? scene : null;
                    });
                  },
                );
              }).toList(),
            ),
            const SizedBox(height: 24),
            // Image picker
            Text(
              '上传图片',
              style: Theme.of(context)
                  .textTheme
                  .titleSmall
                  ?.copyWith(color: palette.textTitle),
            ),
            const SizedBox(height: 8),
            ImagePickerSection(
              images: _images,
              onImagesChanged: (images) {
                setState(() {
                  _images.clear();
                  _images.addAll(images);
                  _result = null;
                  _selectedOutfitIndexForSave = 0;
                  if (images.isNotEmpty) {
                    _wardrobeGarmentIds = [];
                    _wardrobeImageUrls = [];
                  }
                });
                FeatureLocalStore.clear(_cacheKey);
              },
              maxImages: 5,
              hintText: '可选多张（将合并识别后一起推荐）',
              allowMultiple: true,
              onWardrobeTap: () async {
                final picked =
                    await showWardrobePicker(context, multiSelect: true);
                if (picked != null && picked.isNotEmpty) {
                  setState(() {
                    _images.clear();
                    _wardrobeGarmentIds =
                        picked.map((r) => r.garmentId).toList();
                    _wardrobeImageUrls =
                        picked.map((r) => r.imageUrl ?? '').toList();
                    _result = null;
                    _selectedOutfitIndexForSave = 0;
                  });
                  FeatureLocalStore.clear(_cacheKey);
                }
              },
            ),
            const SizedBox(height: 10),
            // 衣橱选择后显示预览图
            if (_wardrobeGarmentIds.isNotEmpty && _wardrobeImageUrls.isNotEmpty)
              SizedBox(
                height: 100,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: _wardrobeImageUrls.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (_, i) {
                    final raw = _wardrobeImageUrls[i];
                    final resolved = resolveGarmentImageUrl(raw,
                            context.read<AuthProvider>().apiClient.baseUrl) ??
                        raw;
                    return Container(
                      width: 100,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: palette.divider),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Stack(
                        children: [
                          Positioned.fill(
                            child: PlatformImage(
                              networkUrl: resolved,
                              fit: BoxFit.cover,
                              placeholder: Center(
                                child: Icon(Icons.checkroom,
                                    color: palette.primary, size: 28),
                              ),
                              errorWidget: Center(
                                child: Icon(Icons.broken_image,
                                    color: palette.textBody, size: 28),
                              ),
                            ),
                          ),
                          if (i == 0)
                            Positioned(
                              left: 4,
                              bottom: 4,
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.55),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: const Text(
                                  '衣橱',
                                  style: TextStyle(
                                      color: Colors.white, fontSize: 10),
                                ),
                              ),
                            ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            if (_images.isNotEmpty || _wardrobeGarmentIds.isNotEmpty)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: palette.primary.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                      color: palette.primary.withValues(alpha: 0.16)),
                ),
                child: Row(
                  children: [
                    Icon(Icons.check_circle_outline,
                        size: 18, color: palette.primary),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _wardrobeGarmentIds.isNotEmpty
                            ? '已从衣橱选择 ${_wardrobeGarmentIds.length} 件衣物，点击生成推荐结果即可查看搭配方案。'
                            : '已选择 ${_images.length} 张图片，点击生成推荐结果即可查看搭配方案。',
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
            const SizedBox(height: 24),
            // Analyze button
            FilledButton.icon(
              onPressed: _isLoading ? null : _analyze,
              icon: _isLoading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.auto_awesome),
              label: Text(_isLoading ? '生成中…' : '生成推荐结果'),
            ),
            const SizedBox(height: 24),
            // Results
            if (_result != null)
              AnalysisResultDisplay(
                result: _result,
                type: 'outfit',
                apiBaseUrl: context.read<AuthProvider>().apiClient.baseUrl,
                onSaveOutfit: _saveSelectedOutfitToCollection,
                saveOutfitLoading: _saveBusy,
                selectedOutfitIndexForSave: _selectedOutfitIndexForSave,
                onSelectedOutfitIndexForSaveChanged: (i) {
                  setState(() => _selectedOutfitIndexForSave = i);
                },
              ),
            if (_result == null && !_isLoading && _images.isNotEmpty) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: palette.surface,
                  borderRadius: BorderRadius.circular(14),
                  border:
                      Border.all(color: palette.divider.withValues(alpha: 0.9)),
                ),
                child: Text(
                  '选好图片后点击“生成推荐结果”，系统会结合场景、衣橱和性别表达指数输出搭配建议。',
                  style: TextStyle(
                    fontSize: 12,
                    color: palette.textBody,
                    height: 1.35,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RecommendHintChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;

  const _RecommendHintChip({
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
