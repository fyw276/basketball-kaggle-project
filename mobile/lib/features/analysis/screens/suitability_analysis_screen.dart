import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart';
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/platform_image.dart';
import '../../../core/widgets/wardrobe_picker_sheet.dart';

class SuitabilityAnalysisScreen extends StatefulWidget {
  const SuitabilityAnalysisScreen({super.key});

  @override
  State<SuitabilityAnalysisScreen> createState() =>
      _SuitabilityAnalysisScreenState();
}

class _SuitabilityAnalysisScreenState extends State<SuitabilityAnalysisScreen> {
  XFile? _image;
  Map<String, dynamic>? _result;
  bool _loading = false;
  String? _selectedScene;
  String? _wardrobeGarmentId;
  String? _wardrobeImageUrl;
  final _scenes = ['日常通勤', '正式场合', '休闲娱乐', '约会聚会', '运动健身', '旅行出游'];

  static const _cacheKey = 'suitability_analysis';

  @override
  void initState() {
    super.initState();
    FeatureLocalStore.loadJson(_cacheKey).then((m) {
      if (m != null && mounted) setState(() => _result = m);
    });
  }

  Future<void> _analyze() async {
    if (_image == null && _wardrobeGarmentId == null) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final auth = context.read<AuthProvider>();
    try {
      final raw = await auth.apiClient.analyzeSuitability(
        imageFile: _wardrobeGarmentId == null ? _image : null,
        garmentId: _wardrobeGarmentId,
        imageUrl: _wardrobeGarmentId == null ? null : _wardrobeImageUrl,
        scene: _selectedScene,
      );
      if (!mounted) return;
      if (raw.containsKey('error')) {
        showAppSnackBar(context, '分析失败：${userFacingApiError(raw['error'])}');
        setState(() => _loading = false);
        return;
      }
      _result = _normalizeResultScene(raw);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '请求异常：${userFacingApiError(e)}');
      }
    }
    if (mounted) {
      setState(() {
        _loading = false;
      });
      final r = _result;
      if (r != null) FeatureLocalStore.saveJson(_cacheKey, r);
    }
  }

  Map<String, dynamic> _normalizeResultScene(Map<String, dynamic> raw) {
    final normalized = Map<String, dynamic>.from(raw);
    final sceneText = normalized['scene']?.toString().trim() ?? '';
    if (sceneText.isEmpty || sceneText == 'null') {
      if (_selectedScene != null && _selectedScene!.isNotEmpty) {
        normalized['scene'] = _selectedScene;
      }
    }
    return normalized;
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return AnalysisFeatureLayout(
      title: '适合度分析',
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
                      Icon(Icons.assessment_outlined,
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
                    '上传单件服装图后，系统会从场景、体型友好度和风格三个维度评估适合度。选择场景后，结果会更贴近你的实际使用场景。',
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
                      _SuitabilityHintChip(
                        label: '场景越明确越准',
                        icon: Icons.location_on_outlined,
                        color: Colors.blue,
                      ),
                      _SuitabilityHintChip(
                        label: '单件清晰图',
                        icon: Icons.photo_outlined,
                        color: Colors.green,
                      ),
                      _SuitabilityHintChip(
                        label: '服装主体完整',
                        icon: Icons.crop_free_outlined,
                        color: Colors.orange,
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // 场景选择
            Row(
              children: [
                Icon(Icons.place_outlined, size: 18, color: palette.primary),
                const SizedBox(width: 8),
                Text(
                  '选择场景',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(color: palette.textTitle),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _scenes.map((s) {
                final sel = _selectedScene == s;
                return ChoiceChip(
                  label: Text(s),
                  selected: sel,
                  selectedColor: palette.chipSelectedBg,
                  labelStyle: TextStyle(
                    color: sel ? palette.chipSelectedLabel : palette.textTitle,
                    fontSize: 13,
                  ),
                  onSelected: (_) =>
                      setState(() => _selectedScene = sel ? null : s),
                );
              }).toList(),
            ),
            if (_selectedScene != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 10,
                ),
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
                        '当前场景：$_selectedScene',
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
            ],
            const SizedBox(height: 16),

            // 图片选择
            Row(
              children: [
                Icon(Icons.image_outlined, size: 18, color: palette.primary),
                const SizedBox(width: 8),
                Text(
                  '上传图片',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(color: palette.textTitle),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ImagePickerSection(
              images: _image != null ? [_image!] : [],
              onImagesChanged: (list) => setState(() {
                _image = list.isEmpty ? null : list.first;
                if (list.isNotEmpty) {
                  _wardrobeGarmentId = null;
                  _wardrobeImageUrl = null;
                }
              }),
              maxImages: 1,
              hintText: '上传服装图片',
              onWardrobeTap: () async {
                final picked = await showWardrobePicker(context);
                if (picked != null && picked.isNotEmpty) {
                  setState(() {
                    _image = null;
                    _wardrobeGarmentId = picked.first.garmentId;
                    _wardrobeImageUrl = picked.first.imageUrl;
                  });
                }
              },
            ),
            const SizedBox(height: 10),
            if (_wardrobeGarmentId != null && _wardrobeImageUrl != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
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
                                  _wardrobeImageUrl,
                                  context
                                      .read<AuthProvider>()
                                      .apiClient
                                      .baseUrl) ??
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
              ),
            if (_image != null)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 10,
                ),
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
                        '已选择图片，点击生成分析结果即可查看适合度结论。',
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

            // 分析按钮
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: ((_image != null || _wardrobeGarmentId != null) &&
                        !_loading)
                    ? _analyze
                    : null,
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
                    : const Icon(Icons.analytics_outlined),
                label: Text(_loading ? '生成中…' : '生成分析结果',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 24),

            // 结果展示
            if (_result != null) ...[
              _SuitabilitySummaryCard(
                result: _result!,
                palette: palette,
                selectedScene: _selectedScene,
              ),
              const SizedBox(height: 12),
              AnalysisResultDisplay(
                result: _result,
                type: 'suitability',
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SuitabilitySummaryCard extends StatelessWidget {
  final Map<String, dynamic> result;
  final dynamic palette;
  final String? selectedScene;

  const _SuitabilitySummaryCard({
    required this.result,
    required this.palette,
    this.selectedScene,
  });

  @override
  Widget build(BuildContext context) {
    final score = (result['overall_score'] is num)
        ? (result['overall_score'] as num).toDouble()
        : 0.0;
    final resultScene = result['scene']?.toString().trim() ?? '';
    final fallbackScene = selectedScene?.trim() ?? '';
    final scene = resultScene.isNotEmpty && resultScene != 'null'
        ? resultScene
        : (fallbackScene.isNotEmpty ? fallbackScene : '未指定');
    final analysis = result['analysis']?.toString() ?? '';
    final scoreColor = score >= 0.8
        ? Colors.green
        : score >= 0.6
            ? Colors.orange
            : Colors.redAccent;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            scoreColor.withValues(alpha: 0.12),
            scoreColor.withValues(alpha: 0.04),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scoreColor.withValues(alpha: 0.28)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: scoreColor.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '综合评分 ${(score * 100).toInt()}%',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    color: scoreColor,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  '当前场景：$scene',
                  style: TextStyle(
                    fontSize: 12,
                    color: palette.textBody,
                    height: 1.35,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            analysis.isNotEmpty ? analysis : '已完成适合度评估。',
            style: TextStyle(
              fontSize: 12,
              color: palette.textBody,
              height: 1.45,
            ),
          ),
        ],
      ),
    );
  }
}

class _SuitabilityHintChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;

  const _SuitabilityHintChip({
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
