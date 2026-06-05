import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/themed_page.dart';
import '../../../core/widgets/platform_image.dart';
import '../../../core/widgets/wardrobe_picker_sheet.dart';
import 'virtual_tryon_screen.dart';

enum _SimilarityMode { single, look }

class SimilarityScreen extends StatefulWidget {
  final bool startInLookMode;
  final bool inspirationLoop;

  const SimilarityScreen({
    super.key,
    this.startInLookMode = false,
    this.inspirationLoop = false,
  });

  @override
  State<SimilarityScreen> createState() => _SimilarityScreenState();
}

class _SimilarityScreenState extends State<SimilarityScreen> {
  final _imagePicker = ImagePicker();

  ApiClient get _apiClient => context.read<AuthProvider>().apiClient;

  XFile? _selectedImage;
  String? _wardrobeGarmentId;
  String? _wardrobeImageUrl;
  bool _isAnalyzing = false;
  bool _isSaving = false;
  _SimilarityMode _mode = _SimilarityMode.single;
  String? _selectedScene;
  Map<String, dynamic>? _analysisResult;
  Map<String, dynamic>? _lookResult;
  Map<String, dynamic>? _lookComplementResult;
  Map<String, dynamic>? _outfitRecommendationResult;

  final List<String> _scenes = const [
    '日常休闲',
    '职场商务',
    '约会聚会',
    '运动健身',
    '正式场合',
  ];

  @override
  void initState() {
    super.initState();
    if (widget.startInLookMode || widget.inspirationLoop) {
      _mode = _SimilarityMode.look;
    }
  }

  Future<ImageSource?> _pickSource() {
    return showModalBottomSheet<ImageSource>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('相册'),
              onTap: () => Navigator.pop(ctx, ImageSource.gallery),
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('相机'),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _pickImage() async {
    try {
      final source = await _pickSource();
      if (source == null) return;
      final image = await _imagePicker.pickImage(
        source: source,
        maxWidth: 1024,
        maxHeight: 1024,
      );
      if (image == null) return;

      setState(() {
        _selectedImage = image;
        _wardrobeGarmentId = null;
        _wardrobeImageUrl = null;
        _analysisResult = null;
        _lookResult = null;
        _lookComplementResult = null;
        _outfitRecommendationResult = null;
      });
    } catch (e) {
      if (!mounted) return;
      showAppSnackBar(
        context,
        '选择图片失败：${userFacingApiError(e)}',
        backgroundColor: Colors.red,
      );
    }
  }

  Future<void> _analyze() async {
    if (_selectedImage == null && _wardrobeGarmentId == null) return;
    setState(() => _isAnalyzing = true);

    try {
      late final Map<String, dynamic> result;
      Map<String, dynamic>? complement;
      Map<String, dynamic>? outfits;
      if (_mode == _SimilarityMode.single) {
        result = _wardrobeGarmentId == null
            ? await _apiClient.analyzeSimilarityFromXFile(_selectedImage!)
            : await _apiClient.analyzeSimilarity(
                garmentId: _wardrobeGarmentId,
                imageUrl: _wardrobeImageUrl,
              );
      } else {
        result = await _apiClient.analyzeLookSimilarity(
          imageFile: _wardrobeGarmentId == null ? _selectedImage : null,
          garmentId: _wardrobeGarmentId,
          imageUrl: _wardrobeImageUrl,
          sourceType: 'photo',
          parserStrategy: 'auto',
          sceneHint: _selectedScene,
          includeTryonCandidates: true,
          includeAccessories: true,
        );
        if (result['error'] == null) {
          complement = await _apiClient.recommendLookComplement(
            imageFile: _wardrobeGarmentId == null ? _selectedImage : null,
            garmentId: _wardrobeGarmentId,
            imageUrl: _wardrobeImageUrl,
            sourceType: 'photo',
            parserStrategy: 'auto',
            sceneHint: _selectedScene,
          );
          final selectedIds = _extractSelectedGarmentIds(result);
          if (selectedIds.isNotEmpty) {
            outfits = await _apiClient.recommendOutfits(
              garmentIds: selectedIds,
              numOutfits: 3,
              scene: _selectedScene,
            );
          }
        }
      }

      if (!mounted) return;
      if (result['error'] != null) {
        showAppSnackBar(
          context,
          '分析失败：${userFacingApiError(result['error'])}',
          backgroundColor: Colors.red,
        );
        return;
      }

      setState(() {
        if (_mode == _SimilarityMode.single) {
          _analysisResult = result;
          _lookResult = null;
        } else {
          _lookResult = result;
          _lookComplementResult = complement;
          _outfitRecommendationResult = outfits;
          _analysisResult = null;
        }
      });
      if (_mode == _SimilarityMode.look) {
        unawaited(_submitLoopFeedback('view', result: result));
      }
    } catch (e) {
      if (!mounted) return;
      showAppSnackBar(
        context,
        '分析失败：${userFacingApiError(e)}',
        backgroundColor: Colors.red,
      );
    } finally {
      if (mounted) setState(() => _isAnalyzing = false);
    }
  }

  Future<void> _pickWardrobeImage() async {
    final picked = await showWardrobePicker(context);
    if (picked == null || picked.isEmpty) return;
    setState(() {
      _selectedImage = null;
      _wardrobeGarmentId = picked.first.garmentId;
      _wardrobeImageUrl = picked.first.imageUrl;
      _analysisResult = null;
      _lookResult = null;
      _lookComplementResult = null;
      _outfitRecommendationResult = null;
    });
  }

  Future<void> _submitLoopFeedback(
    String eventType, {
    Map<String, dynamic>? result,
    String? collectionId,
  }) async {
    final look = result ?? _lookResult;
    if (look == null) return;
    final selectedIds = _extractSelectedGarmentIds(look);
    await _apiClient.submitFeedbackEvent(
      eventType: eventType,
      source: 'vowwear_loop',
      collectionId: collectionId,
      garmentId: selectedIds.isNotEmpty ? selectedIds.first : null,
      scene: _selectedScene,
      payload: {
        'overall_similarity': look['overall_similarity'],
        'coverage_score': look['coverage_score'],
        'scene_hint': _selectedScene,
        'missing_categories': look['missing_categories'] ?? const [],
        'selected_garment_ids': selectedIds,
      },
    );
  }

  Future<void> _saveLookOutfit() async {
    final look = _lookResult;
    if (look == null) return;
    final ids = _extractSelectedGarmentIds(look);
    if (ids.isEmpty) {
      showAppSnackBar(context, '没有可保存的真实衣橱单品');
      return;
    }
    var scene = _selectedScene ?? '灵感穿搭';
    if (scene.length > 50) scene = scene.substring(0, 50);
    setState(() => _isSaving = true);
    try {
      final saveRes = await _apiClient.saveOutfitCollection(
        name: '灵感穿搭 · $scene',
        scene: scene,
        description: '由整身解析 / 分部识别生成，仅保存已有衣橱单品。',
        garmentIds: ids,
      );
      if (!mounted) return;
      if (saveRes['error'] != null) {
        showAppSnackBar(
          context,
          '保存失败：${userFacingApiError(saveRes['error'])}',
          backgroundColor: Colors.red,
        );
        return;
      }
      final collectionId = saveRes['collection_id']?.toString();
      await _submitLoopFeedback('adopt', collectionId: collectionId);
      if (!mounted) return;
      showAppSnackBar(context, '已保存套装');
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = StyleTokens.fromStyle(context.watch<ThemeProvider>().style);

    return ThemedPage(
      appBar: AppBar(
        title: Text('相似度分析', style: tokens.titleStyle.copyWith(fontSize: 18)),
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildIntro(tokens),
            const SizedBox(height: 16),
            _buildModeSwitch(),
            if (_mode == _SimilarityMode.look) ...[
              const SizedBox(height: 16),
              _buildSceneSelector(),
            ],
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pickImage,
                    icon: const Icon(Icons.image),
                    label: const Text('上传参考图'),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pickWardrobeImage,
                    icon: const Icon(Icons.checkroom),
                    label: const Text('选择衣橱图'),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                  ),
                ),
              ],
            ),
            if (_selectedImage != null || _wardrobeGarmentId != null) ...[
              const SizedBox(height: 16),
              _buildSelectedImage(),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: _isAnalyzing ? null : _analyze,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _isAnalyzing
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(
                        _mode == _SimilarityMode.single ? '开始分析' : '开始灵感穿搭分析',
                        style: const TextStyle(fontSize: 16),
                      ),
              ),
            ],
            if (_analysisResult != null) ...[
              const SizedBox(height: 24),
              _buildSingleResult(_analysisResult!),
            ],
            if (_lookResult != null) ...[
              const SizedBox(height: 24),
              _buildLookSummaryCard(_lookResult!),
              const SizedBox(height: 12),
              ...((_lookResult!['parts'] as List? ?? const []).map(
                (part) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _buildLookPartCard(
                      Map<String, dynamic>.from(part as Map)),
                ),
              )),
              _buildMissingCategoriesCard(_lookResult!),
              const SizedBox(height: 12),
              _buildComplementCard(),
              const SizedBox(height: 12),
              _buildTryonCandidatesCard(_lookResult!),
              const SizedBox(height: 12),
              _buildOutfitCandidatesCard(),
              const SizedBox(height: 12),
              _buildLoopActionsCard(_lookResult!),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildIntro(StyleTokens tokens) {
    final text = _mode == _SimilarityMode.single
        ? '上传单品图片，系统会在衣橱中查找相似服饰，帮助避免重复购买。'
        : '上传整身参考图或选择衣橱图，选择场景后进行整身解析 / 分部识别，匹配衣橱、补齐缺失品类，并给出试衣和购买判断。';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: tokens.surface.withValues(alpha: 0.74),
        borderRadius: BorderRadius.circular(tokens.cardRadius),
        border: Border.all(color: tokens.border.withValues(alpha: 0.85)),
        boxShadow: tokens.cardShadow(),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, color: tokens.accent),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: tokens.bodyStyle)),
        ],
      ),
    );
  }

  Widget _buildModeSwitch() {
    return SegmentedButton<_SimilarityMode>(
      segments: const [
        ButtonSegment(
          value: _SimilarityMode.single,
          icon: Icon(Icons.checkroom),
          label: Text('单品'),
        ),
        ButtonSegment(
          value: _SimilarityMode.look,
          icon: Icon(Icons.groups_2_outlined),
          label: Text('Look'),
        ),
      ],
      selected: {_mode},
      onSelectionChanged: (selected) {
        setState(() {
          _mode = selected.first;
          _analysisResult = null;
          _lookResult = null;
        });
      },
    );
  }

  Widget _buildSelectedImage() {
    if (_wardrobeGarmentId != null) {
      final apiBase = _apiClient.baseUrl;
      final imageUrl = resolveGarmentImageUrl(_wardrobeImageUrl, apiBase);
      return Card(
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          height: 260,
          child: PlatformImage(
            networkUrl: imageUrl ?? _wardrobeImageUrl,
            fit: BoxFit.cover,
            placeholder: const Center(child: Icon(Icons.checkroom, size: 44)),
            errorWidget:
                const Center(child: Icon(Icons.broken_image, size: 44)),
          ),
        ),
      );
    }
    return Card(
      clipBehavior: Clip.antiAlias,
      child: FutureBuilder<List<int>>(
        future: _selectedImage!.readAsBytes(),
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            return Image.memory(
              Uint8List.fromList(snapshot.data!),
              height: 300,
              fit: BoxFit.cover,
            );
          }
          return const SizedBox(
            height: 300,
            child: Center(child: CircularProgressIndicator()),
          );
        },
      ),
    );
  }

  Widget _buildSceneSelector() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: _scenes.map((scene) {
        return ChoiceChip(
          label: Text(scene),
          selected: _selectedScene == scene,
          onSelected: (selected) {
            setState(() {
              _selectedScene = selected ? scene : null;
              _lookResult = null;
              _lookComplementResult = null;
              _outfitRecommendationResult = null;
            });
          },
        );
      }).toList(),
    );
  }

  Widget _buildSingleResult(Map<String, dynamic> result) {
    final similar = result['similar_garments'] as List? ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildRecognitionCard(result['target_garment'] as Map?),
        const SizedBox(height: 12),
        if (similar.isEmpty)
          _messageCard(
            icon: Icons.check_circle,
            color: Colors.green,
            text: '没有找到相似服饰，可以放心购买。',
          )
        else
          ...similar.map((raw) =>
              _buildSimilarGarmentCard(Map<String, dynamic>.from(raw as Map))),
        if (result['recommendation'] != null) ...[
          const SizedBox(height: 12),
          _messageCard(
            icon: result['has_duplicate_warning'] == true
                ? Icons.warning
                : Icons.check_circle,
            color: result['has_duplicate_warning'] == true
                ? Colors.orange
                : Colors.green,
            text: result['recommendation'].toString(),
          ),
        ],
      ],
    );
  }

  Widget _buildRecognitionCard(Map? target) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('识别信息',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _buildInfoRow('品类', target?['category']),
            _buildInfoRow('颜色', target?['main_color']?['name']),
            if (target?['style_tags'] is List)
              _buildInfoRow('风格', (target!['style_tags'] as List).join(', ')),
          ],
        ),
      ),
    );
  }

  Widget _buildSimilarGarmentCard(Map<String, dynamic> garment) {
    final imageUrl = _resolveImageUrl(garment['image_url']?.toString());
    final score = (garment['similarity_score'] as num?)?.toDouble() ?? 0.0;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: imageUrl != null
            ? Image.network(imageUrl, width: 60, height: 60, fit: BoxFit.cover)
            : const Icon(Icons.checkroom, size: 40),
        title: Text(garment['category']?.toString() ?? '未分类'),
        subtitle: Text(garment['main_color']?['name']?.toString() ?? ''),
        trailing: _scoreChip(score),
      ),
    );
  }

  Widget _buildLookSummaryCard(Map<String, dynamic> result) {
    final score = (result['overall_similarity'] as num?)?.toDouble() ?? 0.0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Look 整体匹配',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(Icons.analytics_outlined,
                    color: _getSimilarityColor(score)),
                const SizedBox(width: 8),
                Text(
                  '${(score * 100).toStringAsFixed(0)}%',
                  style: const TextStyle(
                      fontSize: 24, fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _buildInfoRow('覆盖', _percent(result['coverage_score'])),
            _buildInfoRow('风格', _percent(result['style_consistency'])),
            _buildInfoRow('配色', _percent(result['color_harmony'])),
            _buildInfoRow('解析策略', result['parser_strategy_used']),
            _buildInfoRow('匹配分部', result['matched_parts_count']),
            const SizedBox(height: 8),
            _messageCard(
              icon: _decisionIcon(result),
              color: _decisionColor(result),
              text: '购买/搭配结论：${_purchaseDecision(result)}',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLookPartCard(Map<String, dynamic> part) {
    final matches = part['matched_garments'] as List? ?? const [];
    final score = (part['similarity'] as num?)?.toDouble() ?? 0.0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.view_agenda_outlined),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    part['part_role']?.toString() ?? '',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ),
                _scoreChip(score),
              ],
            ),
            const SizedBox(height: 8),
            _buildInfoRow('品类', part['detected_category']),
            if (part['style_tags'] is List &&
                (part['style_tags'] as List).isNotEmpty)
              _buildInfoRow('风格', (part['style_tags'] as List).join(', ')),
            if (matches.isNotEmpty) ...[
              const SizedBox(height: 8),
              ...matches.take(3).map((raw) {
                final match = Map<String, dynamic>.from(raw as Map);
                final url = _resolveImageUrl(match['image_url']?.toString());
                final matchScore =
                    (match['similarity_score'] as num?)?.toDouble() ?? 0.0;
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: url != null
                      ? Image.network(url,
                          width: 48, height: 48, fit: BoxFit.cover)
                      : const Icon(Icons.checkroom),
                  title: Text(
                    match['name']?.toString().isNotEmpty == true
                        ? match['name'].toString()
                        : match['category']?.toString() ?? '',
                  ),
                  trailing: _scoreChip(matchScore),
                );
              }),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildMissingCategoriesCard(Map<String, dynamic> result) {
    final missing = result['missing_categories'] as List? ?? const [];
    if (missing.isEmpty) return const SizedBox.shrink();
    return _messageCard(
      icon: Icons.add_shopping_cart,
      color: Colors.orange,
      text: '待补充：${missing.join(', ')}',
    );
  }

  Widget _buildComplementCard() {
    final complement = _lookComplementResult;
    final recommendations = complement?['recommendations'] as List? ?? const [];
    if (recommendations.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('缺失单品建议',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...recommendations.take(5).map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              final category =
                  item['category'] ?? item['missing_category'] ?? item['slot'];
              final reason = item['reason'] ?? item['match_reason'] ?? '';
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.add_shopping_cart_outlined),
                title: Text(category?.toString() ?? '待补充单品'),
                subtitle: reason.toString().trim().isEmpty
                    ? null
                    : Text(reason.toString()),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildTryonCandidatesCard(Map<String, dynamic> result) {
    final candidates =
        result['recommended_tryon_candidates'] as List? ?? const [];
    if (candidates.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('试穿候选',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...candidates.map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.accessibility_new),
                title: Text(item['category']?.toString() ?? ''),
                subtitle: Text(item['part_role']?.toString() ?? ''),
                trailing: IconButton(
                  icon: const Icon(Icons.arrow_forward),
                  onPressed: () => _openTryonCandidate(item),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  void _openTryonCandidate(Map<String, dynamic> item) {
    final imageUrl = item['image_url']?.toString().trim() ?? '';
    if (imageUrl.isEmpty) {
      showAppSnackBar(
        context,
        '该候选缺少图片地址，无法带入试衣',
        backgroundColor: Colors.orange,
      );
      return;
    }

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => VirtualTryonScreen(
          prefilledGarmentId: item['garment_id']?.toString(),
          prefilledGarmentImageUrl: imageUrl,
          prefilledCategory:
              item['category']?.toString() ?? item['part_role']?.toString(),
        ),
      ),
    );
  }

  Widget _buildOutfitCandidatesCard() {
    final result = _outfitRecommendationResult;
    if (result == null || result['error'] != null) {
      return const SizedBox.shrink();
    }
    final rawCards = result['outfit_cards'] ?? result['outfits'];
    if (rawCards is! List || rawCards.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('搭配候选',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...rawCards.take(3).map((raw) {
              final item = Map<String, dynamic>.from(raw as Map);
              final scene =
                  item['scene'] ?? item['recommended_scene'] ?? '场景搭配';
              final description = item['description'] ??
                  item['reason'] ??
                  item['summary'] ??
                  '';
              final score = (item['overall_score'] as num?)?.toDouble();
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.style_outlined),
                title: Text(scene.toString()),
                subtitle: description.toString().trim().isEmpty
                    ? null
                    : Text(description.toString()),
                trailing: score == null ? null : _scoreChip(score),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildLoopActionsCard(Map<String, dynamic> result) {
    final ids = _extractSelectedGarmentIds(result);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              ids.isEmpty ? '当前没有可保存的真实衣橱匹配项' : '将保存 ${ids.length} 件已有衣橱单品',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: ids.isEmpty || _isSaving ? null : _saveLookOutfit,
              icon: _isSaving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.bookmark_add_outlined),
              label: Text(_isSaving ? '保存中…' : '保存套装'),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _submitLoopFeedback('like'),
                    icon: const Icon(Icons.thumb_up_outlined),
                    label: const Text('认可'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _submitLoopFeedback('dislike'),
                    icon: const Icon(Icons.thumb_down_outlined),
                    label: const Text('不认可'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _messageCard(
      {required IconData icon, required Color color, required String text}) {
    return Card(
      color: color.withValues(alpha: 0.08),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, color: color),
            const SizedBox(width: 12),
            Expanded(child: Text(text)),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(width: 60, child: Text('$label:')),
          Expanded(
            child: Text(
              value?.toString() ?? '未知',
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }

  Widget _scoreChip(double score) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: _getSimilarityColor(score),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        '${(score * 100).toStringAsFixed(0)}%',
        style:
            const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
      ),
    );
  }

  Color _getSimilarityColor(double similarity) {
    if (similarity >= 0.8) return Colors.red;
    if (similarity >= 0.6) return Colors.orange;
    return Colors.green;
  }

  String _percent(dynamic value) {
    final n = (value as num?)?.toDouble() ?? 0.0;
    return '${(n * 100).toStringAsFixed(0)}%';
  }

  String? _resolveImageUrl(String? imageUrl) {
    if (imageUrl == null || imageUrl.isEmpty) return null;
    if (imageUrl.startsWith('/')) {
      final serverBaseUrl =
          _apiClient.baseUrl.replaceAll(RegExp(r'/api/v1$'), '');
      return '$serverBaseUrl$imageUrl';
    }
    return imageUrl;
  }

  List<String> _extractSelectedGarmentIds(Map<String, dynamic> result) {
    final ids = <String>[];
    final seen = <String>{};
    final parts = result['parts'] as List? ?? const [];
    for (final rawPart in parts) {
      if (rawPart is! Map) continue;
      final matches = rawPart['matched_garments'] as List? ?? const [];
      if (matches.isEmpty || matches.first is! Map) continue;
      final id = (matches.first as Map)['garment_id']?.toString();
      if (id == null || id.trim().isEmpty || !seen.add(id)) continue;
      ids.add(id);
    }
    return ids;
  }

  String _purchaseDecision(Map<String, dynamic> result) {
    final overall = (result['overall_similarity'] as num?)?.toDouble() ?? 0.0;
    final coverage = (result['coverage_score'] as num?)?.toDouble() ?? 0.0;
    if (overall >= 0.72 && coverage >= 0.65) return '放心尝试';
    if (overall >= 0.45 || coverage >= 0.45) return '对比后尝试';
    return '谨慎购买';
  }

  Color _decisionColor(Map<String, dynamic> result) {
    final decision = _purchaseDecision(result);
    if (decision == '放心尝试') return Colors.green;
    if (decision == '对比后尝试') return Colors.orange;
    return Colors.redAccent;
  }

  IconData _decisionIcon(Map<String, dynamic> result) {
    final decision = _purchaseDecision(result);
    if (decision == '放心尝试') return Icons.check_circle_outline;
    if (decision == '对比后尝试') return Icons.compare_arrows_outlined;
    return Icons.warning_amber_rounded;
  }
}
