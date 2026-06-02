import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart'
    show showAppSnackBar, userFacingApiError;
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart'
    show extractOutfitGarmentIds;
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/wardrobe_picker_sheet.dart';
import '../../../core/widgets/platform_image.dart';
import '../smart_outfit/smart_outfit_cache.dart';
import '../smart_outfit/smart_outfit_controller.dart';
import '../smart_outfit/smart_outfit_geo_weather.dart';
import '../smart_outfit/smart_outfit_widgets.dart';

/// 智能穿搭：参考图 + 自动天气 + 可选情绪 → 3 套衣橱搭配，可重新生成。
/// 定位：浏览器/系统高精度 GPS（非 IP）；地址由服务端逆地理解析；失败时四级行政区选择器降级。
class SmartOutfitScreen extends StatelessWidget {
  final bool autoPickAndGenerate;
  final int initialResultIndex;

  const SmartOutfitScreen({
    super.key,
    this.autoPickAndGenerate = false,
    this.initialResultIndex = 0,
  });

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => SmartOutfitController(),
      child: _SmartOutfitPage(
        autoPickAndGenerate: autoPickAndGenerate,
        initialResultIndex: initialResultIndex,
      ),
    );
  }
}

class _SmartOutfitPage extends StatefulWidget {
  final bool autoPickAndGenerate;
  final int initialResultIndex;

  const _SmartOutfitPage({
    required this.autoPickAndGenerate,
    required this.initialResultIndex,
  });

  @override
  State<_SmartOutfitPage> createState() => _SmartOutfitPageState();
}

class _SmartOutfitPageState extends State<_SmartOutfitPage> {
  final _moodCtrl = TextEditingController();

  int _currentOutfitIndex = 0;
  bool _didJumpToInitialIndex = false;

  /// 1.0 避免 Web 窄屏下右侧露出下一张卡片被裁切；左右留白由卡片 Padding 承担。
  final _pageCtrl = PageController(viewportFraction: 1.0);

  /// 上报「喜欢/采纳」到 `POST /feedback/events`（与场景穿搭页一致）
  bool _outfitFeedbackBusy = false;

  void _handleCredentialInvalid() {
    final auth = context.read<AuthProvider>();
    auth.logout();
    showAppSnackBar(context, '登录已失效，请重新登录后再试');
  }

  Future<void> _sendSmartOutfitFeedback(
    String eventType,
    Map<String, dynamic> outfit,
    int outfitIndex,
  ) async {
    if (_outfitFeedbackBusy) return;
    setState(() => _outfitFeedbackBusy = true);
    try {
      final auth = context.read<AuthProvider>();
      final ids = extractOutfitGarmentIds(outfit);
      final city = context.read<SmartOutfitController>().cityShort.trim();
      final res = await auth.apiClient.submitFeedbackEvent(
        eventType: eventType,
        source: 'smart_outfit',
        garmentId: ids.isNotEmpty ? ids.first : null,
        scene: city.isNotEmpty ? city : null,
        payload: {
          'outfit_index': outfitIndex,
          'garment_ids': ids,
          'mood': _moodCtrl.text.trim(),
        },
      );
      if (!mounted) return;
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
      if (mounted) setState(() => _outfitFeedbackBusy = false);
    }
  }

  @override
  void initState() {
    super.initState();
    Future.microtask(() async {
      if (!mounted) return;
      await context.read<SmartOutfitController>().restoreCacheThenFetchGps(
            context,
            onCredentialInvalid: _handleCredentialInvalid,
          );
    });
    if (widget.autoPickAndGenerate) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _oneTapGenerate();
      });
    }
  }

  @override
  void dispose() {
    _moodCtrl.dispose();
    _pageCtrl.dispose();
    super.dispose();
  }

  Future<void> _cacheTodayRecommendationAt(int index) async {
    final ctrl = context.read<SmartOutfitController>();
    await SmartOutfitHomeRecommendationCache.saveTodayAtIndex(
      outfits: ctrl.outfits,
      index: index,
      cityShort: ctrl.cityShort,
      weather: ctrl.weather,
      temp: ctrl.temp,
    );
  }

  Future<void> _oneTapGenerate() async {
    final ctrl = context.read<SmartOutfitController>();
    if (ctrl.oneTapBusy || ctrl.generating) return;
    ctrl.setOneTapBusy(true);
    try {
      if (ctrl.images.isEmpty &&
          (ctrl.imageUrl == null || ctrl.imageUrl!.isEmpty)) {
        final picked = await _pickSingleImageWithSource();
        if (picked == null) {
          if (mounted) showAppSnackBar(context, '已取消选择图片');
          return;
        }
        if (!mounted) return;
        ctrl.replaceReferenceImages([picked]);
      }
      if (ctrl.weatherLoading) {
        await ctrl.loadWeatherFromGps(
          context,
          onCredentialInvalid: _handleCredentialInvalid,
        );
      }
      if (!mounted) return;
      await _runGenerate(regen: false);
    } finally {
      if (mounted) context.read<SmartOutfitController>().setOneTapBusy(false);
    }
  }

  Future<XFile?> _pickSingleImageWithSource() async {
    final source = await showModalBottomSheet<ImageSource>(
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
    if (source == null) return null;
    final picker = ImagePicker();
    return picker.pickImage(source: source);
  }

  Future<void> _prepareReferenceRecognition() async {
    final auth = context.read<AuthProvider>();
    final ctrl = context.read<SmartOutfitController>();
    if (!auth.isAuthenticated) return;
    try {
      await ctrl.prepareReferenceRecognition(auth.apiClient);
    } catch (e) {
      if (!mounted) return;
      showAppSnackBar(context, '参考图识别失败：${userFacingApiError(e)}');
    }
  }

  Widget _buildReferenceConfirmation(
    SmartOutfitController ctrl,
    dynamic palette,
  ) {
    final hasReference = ctrl.images.isNotEmpty ||
        (ctrl.imageUrl != null && ctrl.imageUrl!.isNotEmpty);
    if (!hasReference) return const SizedBox.shrink();

    const categories = ['上衣', '裤子', '裙子', '外套', '鞋', '包'];
    const colors = ['白', '黑', '粉', '蓝', '灰', '棕', '米色', '红', '绿'];
    final recognition = ctrl.referenceRecognition;
    final confidence = recognition['category_confidence'];
    final confidenceText =
        confidence is num ? ' ${(confidence * 100).toStringAsFixed(0)}%' : '';
    final lowConfidence = recognition['reference_low_confidence'] == true;
    final recognizedCategory =
        recognition['recognized_category']?.toString().trim();

    return Card(
      elevation: 1,
      color: palette.cardBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: palette.divider),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.fact_check_outlined,
                    color: palette.primary, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    ctrl.referenceUploading ? '正在识别参考图…' : '确认参考图',
                    style: TextStyle(
                      color: palette.textTitle,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (confidenceText.isNotEmpty)
                  Text(
                    confidenceText,
                    style: TextStyle(fontSize: 12, color: palette.textBody),
                  ),
              ],
            ),
            if (lowConfidence) ...[
              const SizedBox(height: 6),
              Text(
                recognizedCategory != null && recognizedCategory.isNotEmpty
                    ? '自动识别为 $recognizedCategory，但置信度偏低，请手动确认品类后再生成。'
                    : '识别置信度偏低，请手动确认品类后再生成。',
                style: TextStyle(fontSize: 12, color: palette.textBody),
              ),
            ],
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: categories
                  .map(
                    (cat) => ChoiceChip(
                      label: Text(cat),
                      selected: ctrl.referenceCategory == cat,
                      onSelected: (_) => ctrl.setReferenceCategory(cat),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: colors
                  .map(
                    (color) => ChoiceChip(
                      label: Text(color),
                      selected: ctrl.referenceColorName == color,
                      onSelected: (_) => ctrl.setReferenceColorName(color),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }

  void _maybeJumpToInitialIndex() {
    final outfits = context.read<SmartOutfitController>().outfits;
    if (_didJumpToInitialIndex) return;
    final index = widget.initialResultIndex;
    if (index <= 0 || outfits.isEmpty || index >= outfits.length) {
      _didJumpToInitialIndex = true;
      setState(() => _currentOutfitIndex = 0);
      return;
    }
    _didJumpToInitialIndex = true;
    setState(() => _currentOutfitIndex = index);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_pageCtrl.hasClients) return;
      _pageCtrl.jumpToPage(index);
    });
  }

  Future<void> _runGenerate({required bool regen}) async {
    await SmartOutfitController.waitForAuthReady(context);
    if (!mounted) return;
    final auth = context.read<AuthProvider>();
    final ge = context.read<ThemeProvider>().genderExpression;
    final ctrl = context.read<SmartOutfitController>();
    final r = await ctrl.generateSmartOutfit(
      api: auth.apiClient,
      isAuthenticated: auth.isAuthenticated,
      mood: _moodCtrl.text.trim(),
      genderExpression: ge,
      regen: regen,
    );
    if (!mounted) return;
    switch (r.kind) {
      case SmartOutfitGenerateKind.success:
        setState(() => _currentOutfitIndex = 0);
        _maybeJumpToInitialIndex();
        await _cacheTodayRecommendationAt(_currentOutfitIndex);
        break;
      case SmartOutfitGenerateKind.needImage:
        showAppSnackBar(context, '请先上传一张参考衣物图片');
        break;
      case SmartOutfitGenerateKind.needReferenceCategory:
        showAppSnackBar(context, '识别置信度偏低，请先手动选择参考图品类');
        break;
      case SmartOutfitGenerateKind.notAuthenticated:
        showAppSnackBar(context, '请先登录后再生成穿搭');
        break;
      case SmartOutfitGenerateKind.credentialInvalid:
        _handleCredentialInvalid();
        break;
      case SmartOutfitGenerateKind.apiError:
        final msg = userFacingApiError(r.error);
        final retry = r.connectionRetrySuggested ||
            msg.contains('无法连接') ||
            msg.contains('网络');
        showAppSnackBar(
          context,
          '生成失败：$msg',
          action: retry
              ? SnackBarAction(
                  label: '重试',
                  textColor: Colors.white,
                  onPressed: () => _runGenerate(regen: regen),
                )
              : null,
        );
        break;
      case SmartOutfitGenerateKind.emptyOutfits:
        showAppSnackBar(context, '暂无搭配结果，请重试或向衣橱添加单品');
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    final ctrl = context.watch<SmartOutfitController>();
    final apiBase = context.read<AuthProvider>().apiClient.baseUrl;
    final referencePreviewUrl = resolveGarmentImageUrl(ctrl.imageUrl, apiBase);

    return AnalysisFeatureLayout(
      title: '智能穿搭',
      showGenderBar: true,
      body: LayoutBuilder(
        builder: (context, constraints) {
          final mq = MediaQuery.of(context);
          final availW = constraints.maxWidth;
          final screenH = mq.size.height;
          final maxBodyW = math.min(availW, 520.0);
          final hPad = availW < 360 ? 12.0 : 16.0;
          // 随窗口高度变化；为底栏性别条等留出视觉空间
          final pageViewH = (screenH * 0.38).clamp(240.0, 500.0);

          return Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxBodyW),
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(hPad, 8, hPad, 24),
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
                              Icon(Icons.auto_awesome_rounded,
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
                          const SizedBox(height: 8),
                          Text(
                            '上传一张参考图后，系统会结合当前位置天气、你的性别表达指数与可选心情，一次生成 3 套搭配。',
                            style: TextStyle(
                              fontSize: 12,
                              height: 1.45,
                              color: palette.textBody,
                            ),
                          ),
                          const SizedBox(height: 10),
                          const Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              SmartOutfitHintChip(
                                icon: Icons.add_photo_alternate_outlined,
                                text: '先上传清晰单品图',
                                color: Colors.blue,
                              ),
                              SmartOutfitHintChip(
                                icon: Icons.my_location_outlined,
                                text: '定位越准越贴合天气',
                                color: Colors.green,
                              ),
                              SmartOutfitHintChip(
                                icon: Icons.refresh,
                                text: '支持重新生成对比',
                                color: Colors.orange,
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      '参考衣物',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: palette.textTitle,
                      ),
                    ),
                    const SizedBox(height: 8),
                    ImagePickerSection(
                      images: ctrl.images,
                      onImagesChanged: (list) {
                        context
                            .read<SmartOutfitController>()
                            .replaceReferenceImages(list);
                        setState(() => _didJumpToInitialIndex = false);
                        if (list.isNotEmpty) {
                          _prepareReferenceRecognition();
                        }
                      },
                      maxImages: 1,
                      hintText: '上传 1 张主参考衣物图',
                      allowMultiple: false,
                      selectedImageUrl: referencePreviewUrl,
                      selectedImageLabel: ctrl.referenceSource == 'wardrobe'
                          ? '已从衣橱选择'
                          : '已上传参考图',
                      onSelectedImageRemoved: () {
                        context
                            .read<SmartOutfitController>()
                            .replaceReferenceImages([]);
                        setState(() => _didJumpToInitialIndex = false);
                      },
                      onWardrobeTap: () async {
                        final auth = context.read<AuthProvider>();
                        final smartOutfit =
                            context.read<SmartOutfitController>();
                        final picked = await showWardrobePicker(context);
                        if (!mounted) return;
                        if (picked != null && picked.isNotEmpty) {
                          final url = picked.first.imageUrl;
                          if (url != null && url.isNotEmpty) {
                            final resolved = resolveGarmentImageUrl(
                                url, auth.apiClient.baseUrl);
                            if (resolved != null) {
                              smartOutfit.setWardrobeReference(
                                resolved,
                                category: picked.first.category,
                                mainColorName: picked.first.mainColorName,
                              );
                              setState(() => _didJumpToInitialIndex = false);
                            }
                          }
                        }
                      },
                    ),
                    const SizedBox(height: 10),
                    _buildReferenceConfirmation(ctrl, palette),
                    const SizedBox(height: 20),
                    Text(
                      '定位与天气',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: palette.textTitle,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Card(
                      elevation: 2,
                      shadowColor: palette.primary.withValues(alpha: 0.12),
                      color: palette.cardBg,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(22),
                        side: BorderSide(color: palette.divider),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: ctrl.weatherLoading
                            ? Row(
                                children: [
                                  SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: palette.primary,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      '高精度定位与天气获取中…',
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: palette.textBody,
                                      ),
                                    ),
                                  ),
                                ],
                              )
                            : Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Icon(
                                        smartOutfitWeatherIcon(ctrl.weather),
                                        size: 36,
                                        color: palette.primary,
                                      ),
                                      const SizedBox(width: 12),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              ctrl.weatherFallback
                                                  ? '未精准定位（默认参数）'
                                                  : '已精准定位',
                                              style: TextStyle(
                                                fontWeight: FontWeight.w700,
                                                fontSize: 14,
                                                color: palette.textTitle,
                                              ),
                                            ),
                                            const SizedBox(height: 8),
                                            SmartOutfitStructuredAddressView(
                                              palette: palette,
                                              addressParts: ctrl.addressParts,
                                              fallbackText: ctrl.weatherFallback
                                                  ? '未获取到详细地址'
                                                  : '地址已就绪',
                                            ),
                                            const SizedBox(height: 10),
                                            Text(
                                              '当前天气：${ctrl.weather}',
                                              style: TextStyle(
                                                fontSize: 14,
                                                height: 1.35,
                                                color: palette.textBody,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              '当前温度：${ctrl.temp.toStringAsFixed(0)}℃',
                                              style: TextStyle(
                                                fontSize: 14,
                                                height: 1.35,
                                                color: palette.textBody,
                                              ),
                                            ),
                                            if (ctrl.weatherFallback)
                                              Padding(
                                                padding: const EdgeInsets.only(
                                                    top: 6),
                                                child: Text(
                                                  '已使用默认天气参数',
                                                  style: TextStyle(
                                                    fontSize: 12,
                                                    color: palette.textBody
                                                        .withValues(
                                                            alpha: 0.85),
                                                  ),
                                                ),
                                              ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 12),
                                  Wrap(
                                    spacing: 8,
                                    runSpacing: 8,
                                    alignment: WrapAlignment.end,
                                    children: [
                                      TextButton.icon(
                                        style: TextButton.styleFrom(
                                          foregroundColor: palette.primary,
                                        ),
                                        onPressed: ctrl.weatherRequestInFlight
                                            ? null
                                            : () => ctrl.reloadGpsWeather(
                                                  context,
                                                  onCredentialInvalid:
                                                      _handleCredentialInvalid,
                                                ),
                                        icon: Icon(Icons.my_location,
                                            size: 18, color: palette.primary),
                                        label: const Text('重新获取定位'),
                                      ),
                                      TextButton.icon(
                                        style: TextButton.styleFrom(
                                          foregroundColor: palette.primary,
                                        ),
                                        onPressed: ctrl.weatherLoading
                                            ? null
                                            : () => ctrl.pickManualCityWeather(
                                                  context,
                                                ),
                                        icon: Icon(Icons.map_outlined,
                                            size: 18, color: palette.primary),
                                        label: const Text('手动选择地址'),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      '心情（可选）',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: palette.textTitle,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _moodCtrl,
                      maxLines: 3,
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(
                        hintText: '可选：今天心情如何？告诉我，我为你搭配更贴合情绪的穿搭。',
                        filled: true,
                        fillColor: palette.cardBg,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(22),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(22),
                          borderSide: BorderSide(color: palette.divider),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    SmartOutfitSummaryCard(
                      palette: palette,
                      hasImage: ctrl.images.isNotEmpty ||
                          (ctrl.imageUrl != null && ctrl.imageUrl!.isNotEmpty),
                      weatherLoading: ctrl.weatherLoading,
                      weatherFallback: ctrl.weatherFallback,
                      addressParts: ctrl.addressParts,
                      moodText: _moodCtrl.text.trim(),
                      hasResult: ctrl.outfits.isNotEmpty,
                    ),
                    const SizedBox(height: 20),
                    FilledButton.icon(
                      onPressed: (ctrl.oneTapBusy || ctrl.generating)
                          ? null
                          : _oneTapGenerate,
                      icon: (ctrl.oneTapBusy || ctrl.generating)
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.bolt_rounded),
                      label: Text(
                        (ctrl.oneTapBusy || ctrl.generating)
                            ? '正在一键生成…'
                            : '一键生成穿搭',
                      ),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(22),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (ctrl.outfits.isEmpty)
                      FilledButton.icon(
                        onPressed: ctrl.generating
                            ? null
                            : () => _runGenerate(regen: false),
                        icon: ctrl.generating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.auto_awesome),
                        label: Text(ctrl.generating ? '正在为你生成专属穿搭…' : '生成穿搭'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(22),
                          ),
                        ),
                      )
                    else
                      FilledButton.icon(
                        onPressed: ctrl.generating
                            ? null
                            : () => _runGenerate(regen: true),
                        icon: ctrl.generating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.refresh),
                        label: Text(ctrl.generating ? '正在为你生成专属穿搭…' : '重新生成'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(22),
                          ),
                        ),
                      ),
                    if (ctrl.outfits.isNotEmpty) ...[
                      const SizedBox(height: 24),
                      Text(
                        '搭配方案（左右滑动）',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                          color: palette.textTitle,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: List.generate(ctrl.outfits.length, (index) {
                          final active = index == _currentOutfitIndex;
                          return AnimatedContainer(
                            duration: const Duration(milliseconds: 180),
                            width: active ? 18 : 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: active
                                  ? palette.primary
                                  : palette.divider.withValues(alpha: 0.9),
                              borderRadius: BorderRadius.circular(999),
                            ),
                          );
                        }),
                      ),
                      const SizedBox(height: 8),
                      ScrollConfiguration(
                        behavior: const SmartOutfitMouseDragScrollBehavior(),
                        child: SizedBox(
                          height: pageViewH,
                          child: PageView.builder(
                            controller: _pageCtrl,
                            itemCount: ctrl.outfits.length,
                            onPageChanged: (index) {
                              if (!mounted) return;
                              setState(() {
                                _currentOutfitIndex = index;
                              });
                              _cacheTodayRecommendationAt(index);
                            },
                            itemBuilder: (_, i) {
                              final o = ctrl.outfits[i];
                              final preview =
                                  o['preview_image_url']?.toString() ?? '';
                              final aiRaw = o['ai_recommendation'];
                              final ai = aiRaw is Map
                                  ? Map<String, dynamic>.from(aiRaw)
                                  : const <String, dynamic>{};
                              final aiStyle = ai['style']?.toString() ?? '';
                              final aiScore = (ai['score'] is num)
                                  ? (ai['score'] as num).toDouble()
                                  : double.tryParse('${ai['score']}') ??
                                      ((o['overall_score'] is num)
                                          ? (o['overall_score'] as num)
                                                  .toDouble() *
                                              100
                                          : 0);
                              final reasonsRaw = ai['reasons'];
                              final reasons = reasonsRaw is List
                                  ? reasonsRaw
                                      .map((e) => e.toString().trim())
                                      .where((e) => e.isNotEmpty)
                                      .take(3)
                                      .toList()
                                  : <String>[];
                              final net =
                                  resolveGarmentImageUrl(preview, apiBase);
                              final items = o['items'];
                              final weatherNote =
                                  o['weather_fit_note']?.toString() ??
                                      o['adapter_note']?.toString() ??
                                      '';
                              return Padding(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 4),
                                child: Card(
                                  elevation: 2,
                                  shadowColor:
                                      palette.primary.withValues(alpha: 0.12),
                                  color: palette.cardBg,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(22),
                                  ),
                                  child: ClipRRect(
                                    borderRadius: BorderRadius.circular(22),
                                    child: SingleChildScrollView(
                                      padding: const EdgeInsets.all(14),
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.stretch,
                                        children: [
                                          Row(
                                            children: [
                                              Text(
                                                '搭配 ${i + 1}',
                                                style: TextStyle(
                                                  fontWeight: FontWeight.w800,
                                                  fontSize: 16,
                                                  color: palette.textTitle,
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              if (i == _currentOutfitIndex)
                                                Container(
                                                  padding: const EdgeInsets
                                                      .symmetric(
                                                    horizontal: 8,
                                                    vertical: 3,
                                                  ),
                                                  decoration: BoxDecoration(
                                                    color: palette.primary
                                                        .withValues(
                                                            alpha: 0.12),
                                                    borderRadius:
                                                        BorderRadius.circular(
                                                            999),
                                                  ),
                                                  child: Text(
                                                    '当前',
                                                    style: TextStyle(
                                                      fontSize: 11,
                                                      color: palette.primary,
                                                      fontWeight:
                                                          FontWeight.w700,
                                                    ),
                                                  ),
                                                ),
                                            ],
                                          ),
                                          const SizedBox(height: 8),
                                          if (net != null)
                                            AspectRatio(
                                              aspectRatio: 3 / 4,
                                              child: Container(
                                                decoration: BoxDecoration(
                                                  color: palette.surface,
                                                  borderRadius:
                                                      BorderRadius.circular(18),
                                                ),
                                                clipBehavior: Clip.antiAlias,
                                                child: PlatformImage(
                                                  networkUrl: net,
                                                  fit: BoxFit.contain,
                                                  placeholder: Center(
                                                    child: Icon(Icons.checkroom,
                                                        color: palette.primary,
                                                        size: 48),
                                                  ),
                                                  errorWidget: Container(
                                                    color: palette.surface,
                                                    alignment: Alignment.center,
                                                    child: Column(
                                                      mainAxisSize:
                                                          MainAxisSize.min,
                                                      children: [
                                                        Icon(
                                                          Icons
                                                              .broken_image_outlined,
                                                          color:
                                                              palette.textBody,
                                                          size: 44,
                                                        ),
                                                        const SizedBox(
                                                            height: 6),
                                                        Text(
                                                          '预览图加载失败',
                                                          style: TextStyle(
                                                            fontSize: 12,
                                                            color: palette
                                                                .textBody,
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            )
                                          else
                                            Container(
                                              height: 120,
                                              decoration: BoxDecoration(
                                                color: palette.surface,
                                                borderRadius:
                                                    BorderRadius.circular(14),
                                                border: Border.all(
                                                  color: palette.divider,
                                                ),
                                              ),
                                              alignment: Alignment.center,
                                              child: Text(
                                                '该方案暂无预览图',
                                                style: TextStyle(
                                                  fontSize: 12,
                                                  color: palette.textBody,
                                                ),
                                              ),
                                            ),
                                          const SizedBox(height: 10),
                                          Text(
                                            o['description']?.toString() ?? '',
                                            style: TextStyle(
                                              fontSize: 13,
                                              height: 1.4,
                                              color: palette.textBody,
                                            ),
                                          ),
                                          if (ai.isNotEmpty) ...[
                                            const SizedBox(height: 10),
                                            Container(
                                              padding: const EdgeInsets.all(10),
                                              decoration: BoxDecoration(
                                                color: palette.surface,
                                                borderRadius:
                                                    BorderRadius.circular(12),
                                                border: Border.all(
                                                  color: palette.divider,
                                                ),
                                              ),
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Row(
                                                    children: [
                                                      Text(
                                                        'AI评分 ${aiScore.toStringAsFixed(1)}',
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          fontWeight:
                                                              FontWeight.w700,
                                                          color:
                                                              palette.textTitle,
                                                        ),
                                                      ),
                                                      if (aiStyle
                                                          .isNotEmpty) ...[
                                                        const SizedBox(
                                                            width: 8),
                                                        Container(
                                                          padding:
                                                              const EdgeInsets
                                                                  .symmetric(
                                                            horizontal: 8,
                                                            vertical: 4,
                                                          ),
                                                          decoration:
                                                              BoxDecoration(
                                                            color: palette
                                                                .primary
                                                                .withValues(
                                                                    alpha:
                                                                        0.10),
                                                            borderRadius:
                                                                BorderRadius
                                                                    .circular(
                                                                        999),
                                                          ),
                                                          child: Text(
                                                            aiStyle,
                                                            style: TextStyle(
                                                              fontSize: 11,
                                                              color: palette
                                                                  .primary,
                                                              fontWeight:
                                                                  FontWeight
                                                                      .w600,
                                                            ),
                                                          ),
                                                        ),
                                                      ],
                                                    ],
                                                  ),
                                                  if (reasons.isNotEmpty) ...[
                                                    const SizedBox(height: 8),
                                                    ...reasons
                                                        .asMap()
                                                        .entries
                                                        .map(
                                                          (entry) => Padding(
                                                            padding:
                                                                const EdgeInsets
                                                                    .only(
                                                                    bottom: 4),
                                                            child: Text(
                                                              '${entry.key + 1}. ${entry.value}',
                                                              style: TextStyle(
                                                                fontSize: 12,
                                                                height: 1.35,
                                                                color: palette
                                                                    .textBody,
                                                              ),
                                                            ),
                                                          ),
                                                        ),
                                                  ],
                                                ],
                                              ),
                                            ),
                                          ],
                                          if (weatherNote.isNotEmpty) ...[
                                            const SizedBox(height: 8),
                                            Text(
                                              '适配说明：$weatherNote',
                                              style: TextStyle(
                                                fontSize: 12,
                                                height: 1.35,
                                                color: palette.textBody
                                                    .withValues(alpha: 0.95),
                                              ),
                                            ),
                                          ],
                                          if (items is List &&
                                              items.isNotEmpty) ...[
                                            const SizedBox(height: 12),
                                            Text(
                                              '单品',
                                              style: TextStyle(
                                                fontWeight: FontWeight.w700,
                                                color: palette.textTitle,
                                              ),
                                            ),
                                            const SizedBox(height: 6),
                                            ...items.map<Widget>((it) {
                                              final m =
                                                  Map<String, dynamic>.from(
                                                      it as Map);
                                              final colorHint =
                                                  m['color_hint']?.toString() ??
                                                      '';
                                              final iu =
                                                  m['image_url']?.toString() ??
                                                      '';
                                              final iurl =
                                                  resolveGarmentImageUrl(
                                                      iu, apiBase);
                                              return Padding(
                                                padding: const EdgeInsets.only(
                                                    bottom: 10),
                                                child: Row(
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.start,
                                                  children: [
                                                    ClipRRect(
                                                      borderRadius:
                                                          BorderRadius.circular(
                                                              12),
                                                      child: SizedBox(
                                                        width: 56,
                                                        height: 56,
                                                        child: iurl != null
                                                            ? PlatformImage(
                                                                networkUrl:
                                                                    iurl,
                                                                fit: BoxFit
                                                                    .contain,
                                                              )
                                                            : ColoredBox(
                                                                color: palette
                                                                    .primary
                                                                    .withValues(
                                                                        alpha:
                                                                            0.08),
                                                              ),
                                                      ),
                                                    ),
                                                    const SizedBox(width: 10),
                                                    Expanded(
                                                      child: Column(
                                                        crossAxisAlignment:
                                                            CrossAxisAlignment
                                                                .start,
                                                        children: [
                                                          Text(
                                                            m['name']
                                                                    ?.toString() ??
                                                                m['category']
                                                                    ?.toString() ??
                                                                '',
                                                            maxLines: 2,
                                                            overflow:
                                                                TextOverflow
                                                                    .ellipsis,
                                                            style: TextStyle(
                                                              fontWeight:
                                                                  FontWeight
                                                                      .w600,
                                                              color: palette
                                                                  .textTitle,
                                                              fontSize: colorHint
                                                                      .isNotEmpty
                                                                  ? 13.5
                                                                  : null,
                                                            ),
                                                          ),
                                                          Text(
                                                            m['category']
                                                                    ?.toString() ??
                                                                '',
                                                            style: TextStyle(
                                                              fontSize: 12,
                                                              color: palette
                                                                  .textBody
                                                                  .withValues(
                                                                alpha: colorHint
                                                                        .isNotEmpty
                                                                    ? 0.55
                                                                    : 1.0,
                                                              ),
                                                            ),
                                                          ),
                                                          if (colorHint
                                                              .isNotEmpty)
                                                            Padding(
                                                              padding:
                                                                  const EdgeInsets
                                                                      .only(
                                                                      top: 2),
                                                              child: Text(
                                                                colorHint,
                                                                style:
                                                                    TextStyle(
                                                                  fontSize: 11,
                                                                  height: 1.25,
                                                                  color: palette
                                                                      .textBody
                                                                      .withValues(
                                                                          alpha:
                                                                              0.72),
                                                                ),
                                                              ),
                                                            ),
                                                        ],
                                                      ),
                                                    ),
                                                  ],
                                                ),
                                              );
                                            }),
                                          ],
                                          const SizedBox(height: 12),
                                          Row(
                                            children: [
                                              Expanded(
                                                child: OutlinedButton.icon(
                                                  onPressed: _outfitFeedbackBusy
                                                      ? null
                                                      : () =>
                                                          _sendSmartOutfitFeedback(
                                                            'like',
                                                            Map<String,
                                                                dynamic>.from(o),
                                                            i,
                                                          ),
                                                  icon: _outfitFeedbackBusy
                                                      ? const SizedBox(
                                                          width: 16,
                                                          height: 16,
                                                          child:
                                                              CircularProgressIndicator(
                                                            strokeWidth: 2,
                                                          ),
                                                        )
                                                      : const Icon(
                                                          Icons.favorite_border,
                                                          size: 18,
                                                        ),
                                                  label: const Text('喜欢'),
                                                ),
                                              ),
                                              const SizedBox(width: 10),
                                              Expanded(
                                                child: FilledButton.tonalIcon(
                                                  onPressed: _outfitFeedbackBusy
                                                      ? null
                                                      : () =>
                                                          _sendSmartOutfitFeedback(
                                                            'adopt',
                                                            Map<String,
                                                                dynamic>.from(o),
                                                            i,
                                                          ),
                                                  icon: const Icon(
                                                    Icons.check_circle_outline,
                                                    size: 18,
                                                  ),
                                                  label: const Text('采纳'),
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 4),
                                          Text(
                                            '记录后将用于推荐优化与数据统计',
                                            style: TextStyle(
                                              fontSize: 11,
                                              color: palette.textBody
                                                  .withValues(alpha: 0.85),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
