// ignore_for_file: prefer_const_constructors

import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/services/image_saver.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/platform_image.dart';

/// 衣物品类（传给后端 `garment_category`，用于百炼等路由）
enum _GarmentCategoryChoice {
  auto,
  top,
  bottom,
  skirt,
  outfit,
}

/// 试衣质量模式枚举
enum _TryOnQualityMode {
  professional, // CatVTON 深度学习 + 颜色保真（真实贴合，细节完整）
  hybrid, // Warp保真 + CatVTON光影增强（100%图案保留 + 自然贴合）
  paste, // 白底标准图专用：自动旋转 + 身体比例缩放 + 几何贴合
}

extension _TryOnQualityModeApi on _TryOnQualityMode {
  /// 传给 /garment 端点的 mode 值
  String get apiValue {
    switch (this) {
      case _TryOnQualityMode.professional:
        return 'detail_fidelity';
      case _TryOnQualityMode.hybrid:
        return 'hybrid';
      case _TryOnQualityMode.paste:
        return 'paste';
    }
  }

  /// 传给 /validate-input 端点的 mode 值（该端点接受 professional/hybrid）
  String get validateApiValue {
    switch (this) {
      case _TryOnQualityMode.professional:
        return 'professional';
      case _TryOnQualityMode.hybrid:
        return 'hybrid';
      case _TryOnQualityMode.paste:
        return 'paste';
    }
  }

  String get label {
    switch (this) {
      case _TryOnQualityMode.professional:
        return '细节保真';
      case _TryOnQualityMode.hybrid:
        return '混合模式';
      case _TryOnQualityMode.paste:
        return '标准图粘贴';
    }
  }

  String get description {
    switch (this) {
      case _TryOnQualityMode.professional:
        return 'CatVTON 深度学习试衣 + 颜色保真增强；'
            '真实贴合衣服光影，颜色和图案细节完整保留';
      case _TryOnQualityMode.hybrid:
        return 'Warp保真（100%衣服图案/颜色）+ CatVTON光影增强；'
            '衣服区域完全保留原始颜色和图案，同时叠加AI生成的自然光影和褶皱效果';
      case _TryOnQualityMode.paste:
        return '白底标准图专用：自动旋转衣服方向 + 按身体比例缩放 + 几何贴合；'
            '适合商品平铺白底图，无需AI深度学习，处理最快';
    }
  }
}

extension _GarmentCategoryChoiceApi on _GarmentCategoryChoice {
  /// 为 null 时不传表单字段，由后端自动推断
  String? get apiValue {
    switch (this) {
      case _GarmentCategoryChoice.auto:
        return null;
      case _GarmentCategoryChoice.top:
        return '上装';
      case _GarmentCategoryChoice.bottom:
        return '下装';
      case _GarmentCategoryChoice.skirt:
        return '裙装';
      case _GarmentCategoryChoice.outfit:
        return '套装';
    }
  }

  String get label {
    switch (this) {
      case _GarmentCategoryChoice.auto:
        return '自动识别';
      case _GarmentCategoryChoice.top:
        return '上装';
      case _GarmentCategoryChoice.bottom:
        return '下装';
      case _GarmentCategoryChoice.skirt:
        return '裙装';
      case _GarmentCategoryChoice.outfit:
        return '上衣+下装';
    }
  }
}

/// 虚拟试衣：上传衣服图 + 人物照（建议全身正面），单次请求生成一张结果图。
/// 品类（上装/下装/裙装）用于后端与专用 VTON 路由；试裤子时请选手动「下装」。
class VirtualTryonScreen extends StatefulWidget {
  final String? prefilledGarmentId;
  final String? prefilledGarmentImageUrl;
  final String? prefilledCategory;

  const VirtualTryonScreen({
    super.key,
    this.prefilledGarmentId,
    this.prefilledGarmentImageUrl,
    this.prefilledCategory,
  });

  @override
  State<VirtualTryonScreen> createState() => _VirtualTryonScreenState();
}

class _VirtualTryonScreenState extends State<VirtualTryonScreen> {
  XFile? _garmentImage;
  XFile? _garmentImage2;
  String? _standardizedGarmentUrl;
  String? _standardizedGarmentUrl2;
  String? _garmentQualityHint;
  XFile? _personFront;
  _GarmentCategoryChoice _garmentCategory = _GarmentCategoryChoice.auto;
  _TryOnQualityMode _qualityMode = _TryOnQualityMode.hybrid;
  bool _loading = false;
  bool _usedFallback = false;
  bool? _precheckPassed;
  String? _precheckMessage;
  String? _precheckHint;
  String? _precheckErrorCode;
  Map<String, double> _precheckScores = const {};
  Map<String, double> _precheckThresholds = const {};
  String? _precheckSource;

  /// 试衣结果图 URL 列表（当前为单次生成，通常 1 张；保留列表以兼容轮播）
  List<String> _results = [];
  int _currentIndex = 0;
  final _pageCtrl = PageController();
  final _aspectRatioCache = <String, double>{};

  static const _cacheKey = 'virtual_tryon';
  static const _carouselDotRadius = BorderRadius.all(Radius.circular(4));

  String? get _prefilledGarmentId {
    final value = widget.prefilledGarmentId?.trim();
    return value == null || value.isEmpty ? null : value;
  }

  @override
  void initState() {
    super.initState();
    final prefilledUrl = widget.prefilledGarmentImageUrl;
    if (prefilledUrl != null && prefilledUrl.trim().isNotEmpty) {
      _standardizedGarmentUrl = prefilledUrl.trim();
      _garmentCategory = _choiceFromTryonCategory(widget.prefilledCategory);
      if (_garmentCategory == _GarmentCategoryChoice.bottom) {
        _qualityMode = _TryOnQualityMode.professional;
      }
      _garmentQualityHint = '已从 Look 分析预填待试穿衣物';
    }
    FeatureLocalStore.loadJson(_cacheKey).then((m) {
      if (m == null || !mounted) return;
      final list = m['results'];
      if (list is List && list.isNotEmpty) {
        setState(() {
          _results = list.map((e) => e.toString()).toList();
        });
      }
    });
  }

  @override
  void dispose() {
    _pageCtrl.dispose();
    super.dispose();
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

  Future<void> _pickGarment() async {
    final source = await _pickSource();
    if (source == null) return;
    final picker = ImagePicker();
    final img = await picker.pickImage(source: source);
    if (img != null) {
      setState(() {
        _garmentImage = img;
        _garmentQualityHint = '正在评估衣服图是否适合试衣...';
        _standardizedGarmentUrl = null;
        _resetPrecheckPanel();
      });
      final hint = await _evaluateGarmentQuality(img);
      if (!mounted) return;
      setState(() {
        _garmentQualityHint = hint;
      });
      await _autoPreprocessGarment(primary: true);
    }
  }

  Future<void> _pickGarment2() async {
    final source = await _pickSource();
    if (source == null) return;
    final picker = ImagePicker();
    final img = await picker.pickImage(source: source);
    if (img != null) {
      setState(() {
        _garmentImage2 = img;
        _standardizedGarmentUrl2 = null;
      });
      await _autoPreprocessGarment(primary: false);
    }
  }

  _GarmentCategoryChoice _choiceFromTryonCategory(String? c) {
    final low = (c ?? '').trim().toLowerCase();
    if (low == 'top' || low.contains('上')) return _GarmentCategoryChoice.top;
    if (low == 'bottom' || low.contains('下') || low.contains('裤')) {
      return _GarmentCategoryChoice.bottom;
    }
    if (low == 'skirt' || low.contains('裙') || low.contains('dress')) {
      return _GarmentCategoryChoice.skirt;
    }
    return _GarmentCategoryChoice.auto;
  }

  Future<void> _autoPreprocessGarment({required bool primary}) async {
    final auth = context.read<AuthProvider>();
    if (!auth.isInitialized || !auth.isAuthenticated) {
      return;
    }
    final file = primary ? _garmentImage : _garmentImage2;
    if (file == null) return;

    final res = await auth.apiClient.tryonV2Preprocess(garmentImage: file);
    if (!mounted) return;
    if (res['error'] != null) {
      // Do not block user; surface hint softly via precheck panel.
      setState(() {
        _precheckPassed = false;
        _precheckMessage = '预处理失败：${res['error']}';
        _precheckHint = res['action_hint']?.toString();
        _precheckErrorCode = res['error_code']?.toString();
        _precheckSource = 'preprocess';
      });
      return;
    }

    final url =
        (res['preview_white_url'] ?? res['standardized_image_url'])?.toString();
    final cat = res['tryon_category']?.toString();
    setState(() {
      if (primary) {
        _standardizedGarmentUrl = url;
        // Only auto-fill category when user left it as「自动识别」.
        // Manual 下装/上装 must not be overwritten by low-confidence CLIP (e.g. pants→裙子).
        if (_garmentCategory == _GarmentCategoryChoice.auto) {
          _garmentCategory = _choiceFromTryonCategory(cat);
        }
      } else {
        _standardizedGarmentUrl2 = url;
      }
      _precheckPassed = true;
      _precheckMessage = '预处理完成：已生成白底标准图并识别品类';
      _precheckHint = cat != null ? '识别品类：$cat' : null;
      _precheckErrorCode = null;
      _precheckSource = 'preprocess';
    });
  }

  Future<void> _pickPerson() async {
    final source = await _pickSource();
    if (source == null) return;
    final picker = ImagePicker();
    final img = await picker.pickImage(source: source);
    if (img != null) {
      setState(() {
        _personFront = img;
        _resetPrecheckPanel();
      });
    }
  }

  void _resetPrecheckPanel() {
    _precheckPassed = null;
    _precheckMessage = null;
    _precheckHint = null;
    _precheckErrorCode = null;
    _precheckScores = const {};
    _precheckThresholds = const {};
    _precheckSource = null;
  }

  Map<String, double> _toScoreMap(dynamic raw) {
    if (raw is! Map) return const {};
    final out = <String, double>{};
    raw.forEach((k, v) {
      final parsed = double.tryParse(v.toString());
      if (parsed != null) {
        out[k.toString()] = parsed;
      }
    });
    return out;
  }

  Future<void> _generate() async {
    final hasPrimaryGarment = _garmentImage != null ||
        (_standardizedGarmentUrl?.trim().isNotEmpty ?? false) ||
        _prefilledGarmentId != null;
    if (!hasPrimaryGarment || _personFront == null) return;
    if (_garmentCategory == _GarmentCategoryChoice.outfit &&
        _garmentImage2 == null &&
        (_standardizedGarmentUrl2?.trim().isNotEmpty ?? false) == false) {
      if (mounted) {
        showAppSnackBar(context, '已选择「上衣+下装」，请再上传第二件（下装/裙装）');
      }
      return;
    }

    final auth = context.read<AuthProvider>();
    if (!auth.isInitialized) {
      if (mounted) {
        showAppSnackBar(context, '正在加载登录状态，请稍后再试');
      }
      return;
    }
    if (!auth.isAuthenticated) {
      if (mounted) {
        showAppSnackBar(
          context,
          '请先登录后再使用虚拟试衣（试衣结果会保存到您的账号）',
        );
      }
      return;
    }

    // Enter loading state early so "precheck" doesn't look like no-op.
    setState(() {
      _loading = true;
    });

    final precheckError = await _precheckTryOnInputs(auth.apiClient);
    if (precheckError != null) {
      if (mounted) {
        setState(() {
          _loading = false;
        });
        showAppSnackBar(context, precheckError);
      }
      return;
    }

    // 新生成时清空旧结果与本地缓存，避免“看起来没对应/还是旧图”的错觉
    FeatureLocalStore.saveJson(_cacheKey, {'results': []});
    setState(() {
      _results = [];
      _usedFallback = false;
    });

    final base = auth.apiClient.baseUrl;
    try {
      final raw = await _requestTryOn(auth);
      final map = Map<String, dynamic>.from(raw as Map<dynamic, dynamic>);
      if (map['error'] != null) {
        final hint = map['action_hint']?.toString();
        final msg = hint != null && hint.trim().isNotEmpty
            ? '${userFacingApiError(map['error'])}（建议：$hint）'
            : userFacingApiError(map['error']);
        if (mounted) {
          showAppSnackBar(context, '试衣失败：$msg');
        }
        setState(() {
          _loading = false;
        });
        return;
      }

      if (map['status']?.toString() == 'error') {
        if (mounted) {
          showAppSnackBar(
            context,
            map['message']?.toString() ?? '试衣失败',
          );
        }
        setState(() {
          _loading = false;
        });
        return;
      }

      final status = map['status']?.toString();
      if (status == 'fallback') {
        _usedFallback = true;
      }

      final resultUrl = map['result_image_url']?.toString();
      final resolved = resolveGarmentImageUrl(resultUrl, base);
      _results = resolved != null && resolved.isNotEmpty ? [resolved] : [];
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '请求失败：${userFacingApiError(e)}');
      }
    }

    if (!mounted) return;
    setState(() {
      _loading = false;
      _currentIndex = 0;
    });
    if (_usedFallback && mounted) {
      showAppSnackBar(
        context,
        '当前为“简化合成模式”（模型未加载成功），效果会像叠图。请先下载/配置 try-on 模型后重试。',
      );
    }
    if (_results.isNotEmpty) {
      FeatureLocalStore.saveJson(_cacheKey, {'results': _results});
    }
  }

  Future<Map<String, dynamic>> _requestTryOn(AuthProvider auth) async {
    final cat = (_garmentCategory.apiValue ?? 'auto').trim();
    var mode = _qualityMode.apiValue;
    final isOutfit = _garmentCategory == _GarmentCategoryChoice.outfit;
    final isBottom = _garmentCategory == _GarmentCategoryChoice.bottom;

    // Never let pants fall through as auto/top or paste/stable_fast.
    final resolvedCategory = isOutfit
        ? 'outfit'
        : (isBottom ? 'bottom' : (cat.isEmpty ? 'auto' : cat));
    if (isBottom && mode == 'paste') {
      mode = 'detail_fidelity';
    }

    final v2 = await auth.apiClient.virtualTryonV2Garment(
      garmentImage: _garmentImage,
      garmentImage2: isOutfit ? _garmentImage2 : null,
      personImage: _personFront,
      garmentId: _prefilledGarmentId,
      garmentCategory: resolvedCategory,
      garmentCategory2: 'bottom',
      garmentImageUrl: _standardizedGarmentUrl,
      garmentImageUrl2: isOutfit ? _standardizedGarmentUrl2 : null,
      mode: mode,
    );

    if (v2['error'] == null) {
      return v2;
    }

    final code = v2['error_code']?.toString();
    final msg = v2['error']?.toString() ?? '';
    final disabledByServer =
        code == 'TRYON_V2_DISABLED' || msg.contains('v2 未启用');
    final v2NotFound = msg.contains('/tryon/pants') && msg.contains('404');
    if (disabledByServer || v2NotFound) {
      return auth.apiClient.virtualTryon(
        garmentImage: _garmentImage,
        personImage: _personFront,
        garmentId: _prefilledGarmentId,
        imageUrl: _standardizedGarmentUrl,
        garmentCategory: _garmentCategory.apiValue,
      );
    }
    return v2;
  }

  Future<void> _saveCurrentResult() async {
    if (_results.isEmpty) return;
    final index = _currentIndex.clamp(0, _results.length - 1);
    final uri = Uri.parse(_results[index]);

    try {
      if (kIsWeb) {
        final opened = await launchUrl(uri, webOnlyWindowName: '_blank');
        if (!opened) throw Exception('无法打开图片下载链接');
      } else {
        final response = await http.get(uri);
        if (response.statusCode < 200 || response.statusCode >= 300) {
          throw Exception('图片下载失败：HTTP ${response.statusCode}');
        }
        await saveImageToGallery(response.bodyBytes, album: '智能穿搭助手');
      }

      if (!mounted) return;
      showAppSnackBar(context, kIsWeb ? '已在新标签页打开试衣图' : '已保存到相册');
    } catch (e) {
      if (!mounted) return;
      showAppSnackBar(
        context,
        '保存失败：${userFacingApiError(e)}',
        backgroundColor: Colors.red,
      );
    }
  }

  Future<String?> _precheckTryOnInputs(dynamic apiClient) async {
    final garment = _garmentImage;
    final person = _personFront;
    final hasGarmentUrl = _standardizedGarmentUrl?.trim().isNotEmpty ?? false;
    final hasGarmentId = _prefilledGarmentId != null;
    if ((garment == null && !hasGarmentUrl && !hasGarmentId) ||
        person == null) {
      return '请先上传衣服图和人物照';
    }
    if (_garmentCategory == _GarmentCategoryChoice.outfit &&
        _garmentImage2 == null &&
        (_standardizedGarmentUrl2?.trim().isNotEmpty ?? false) == false) {
      return '已选择「上衣+下装」，请再上传第二件（下装/裙装）';
    }

    final garmentCheck = garment == null ? null : await _inspectImage(garment);
    if (garmentCheck != null) {
      if (mounted) {
        setState(() {
          _precheckPassed = false;
          _precheckMessage = garmentCheck;
          _precheckHint = '请优先替换为无模特白底商品图';
          _precheckErrorCode = 'LOCAL_GARMENT_PRECHECK_FAILED';
          _precheckScores = const {};
          _precheckThresholds = const {};
          _precheckSource = 'local';
        });
      }
      return garmentCheck;
    }

    final personCheck = await _inspectImage(person);
    if (personCheck != null) {
      if (mounted) {
        setState(() {
          _precheckPassed = false;
          _precheckMessage = personCheck;
          _precheckHint = '请上传更清晰、全身正面的站姿照片';
          _precheckErrorCode = 'LOCAL_PERSON_PRECHECK_FAILED';
          _precheckScores = const {};
          _precheckThresholds = const {};
          _precheckSource = 'local';
        });
      }
      return personCheck;
    }

    final category = (_garmentCategory.apiValue ?? 'auto').trim();
    final mode = _qualityMode.validateApiValue;
    final isOutfit = _garmentCategory == _GarmentCategoryChoice.outfit;
    final remote = await apiClient.tryonV2ValidateInput(
      garmentImage: garment,
      garmentImage2: isOutfit ? _garmentImage2 : null,
      personImage: person,
      garmentId: _prefilledGarmentId,
      garmentImageUrl: _standardizedGarmentUrl,
      garmentImageUrl2: isOutfit ? _standardizedGarmentUrl2 : null,
      garmentCategory: isOutfit ? 'outfit' : category,
      garmentCategory2: 'bottom',
      mode: mode,
    );

    final remoteError = remote['error'];
    if (remoteError != null) {
      final code = remote['error_code']?.toString() ?? '';
      final msg = remoteError.toString();
      // 服务端未启用 v2 时，不阻断，转为兼容旧链路。
      if (code == 'TRYON_V2_DISABLED' || msg.contains('v2 未启用')) {
        if (mounted) {
          setState(() {
            _precheckPassed = null;
            _precheckMessage = '服务端未启用 v2 预检，已使用兼容链路';
            _precheckHint = null;
            _precheckErrorCode = null;
            _precheckScores = const {};
            _precheckThresholds = const {};
            _precheckSource = 'compat';
          });
        }
        return null;
      }
      final hint = remote['action_hint']?.toString();
      if (mounted) {
        setState(() {
          _precheckPassed = false;
          _precheckMessage = msg;
          _precheckHint = hint;
          _precheckErrorCode = code.isEmpty ? null : code;
          _precheckScores = _toScoreMap(remote['qc_scores']);
          _precheckThresholds = const {};
          _precheckSource = 'remote';
        });
      }
      if (hint != null && hint.trim().isNotEmpty) {
        return '预检失败：$msg（建议：$hint）';
      }
      return '预检失败：$msg';
    }

    final passed =
        remote['passed'] == true || remote['status']?.toString() == 'pass';
    if (mounted) {
      setState(() {
        _precheckPassed = passed;
        _precheckMessage = remote['message']?.toString();
        _precheckHint = remote['action_hint']?.toString();
        _precheckErrorCode = remote['error_code']?.toString();
        _precheckScores = _toScoreMap(remote['qc_scores']);
        _precheckThresholds = _toScoreMap(remote['thresholds']);
        _precheckSource = 'remote';
      });
    }
    if (!passed) {
      final msg = remote['message']?.toString() ?? '输入未通过试衣预检';
      final hint = remote['action_hint']?.toString();
      if (hint != null && hint.trim().isNotEmpty) {
        return '$msg（建议：$hint）';
      }
      return msg;
    }

    return null;
  }

  Future<String?> _evaluateGarmentQuality(XFile file) async {
    try {
      final bytes = await file.readAsBytes();
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final width = frame.image.width;
      final height = frame.image.height;

      if (bytes.length < 12 * 1024) {
        return '适配度：较低，图片太小，建议换更清晰的商品图';
      }
      if (width < 256 || height < 256) {
        return '适配度：较低，分辨率偏低，建议至少 256px 以上';
      }

      final isPortrait = height > width * 1.15;
      final isLargeEnough = bytes.length > 80 * 1024;
      if (isPortrait && isLargeEnough) {
        final signals = await _estimateGarmentPhotoSignals(frame.image);
        if (signals.veryLikelyPerson) {
          return '适配度：较低，疑似人物照，建议换无模特白底商品图';
        }
        if (signals.likelyPerson) {
          return '适配度：中等，疑似含人物元素，建议优先使用无模特商品图';
        }
      }

      if (width >= 512 && height >= 512) {
        return '适配度：较高，适合试衣';
      }
      return '适配度：中等，建议再找一张更清晰的商品图';
    } catch (_) {
      return '适配度：未知，后端会继续做校验';
    }
  }

  void _showTryOnTips() {
    showDialog<void>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('建议上传图样'),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _TipRow(
                icon: Icons.check_circle_outline,
                color: Colors.green,
                title: '推荐',
                text: '无模特、白底、主体清晰、占画面比例较大的商品图。',
              ),
              SizedBox(height: 10),
              _TipRow(
                icon: Icons.remove_circle_outline,
                color: Colors.orange,
                title: '谨慎',
                text: '纯色背景、轻微裁切但衣服主体完整的图片。',
              ),
              SizedBox(height: 10),
              _TipRow(
                icon: Icons.cancel_outlined,
                color: Colors.redAccent,
                title: '不推荐',
                text: '含模特、多人、自拍、海报拼图、分辨率过低的图片。',
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('知道了'),
            ),
          ],
        );
      },
    );
  }

  _TryOnQualityLevel _garmentQualityLevel(String? hint) {
    final text = (hint ?? '').toLowerCase();
    if (text.contains('较高') || text.contains('适合试衣')) {
      return _TryOnQualityLevel.good;
    }
    if (text.contains('较低') || text.contains('不建议') || text.contains('像人物照')) {
      return _TryOnQualityLevel.poor;
    }
    if (text.contains('中等') || text.contains('未知')) {
      return _TryOnQualityLevel.medium;
    }
    return _TryOnQualityLevel.unknown;
  }

  Color _garmentQualityColor(String? hint, Palette palette) {
    switch (_garmentQualityLevel(hint)) {
      case _TryOnQualityLevel.good:
        return Colors.green;
      case _TryOnQualityLevel.medium:
        return Colors.orange;
      case _TryOnQualityLevel.poor:
        return Colors.redAccent;
      case _TryOnQualityLevel.unknown:
        return palette.accent;
    }
  }

  String _garmentQualityTitle(String? hint) {
    switch (_garmentQualityLevel(hint)) {
      case _TryOnQualityLevel.good:
        return '可直接试衣';
      case _TryOnQualityLevel.medium:
        return '建议优化后再试';
      case _TryOnQualityLevel.poor:
        return '不建议试衣';
      case _TryOnQualityLevel.unknown:
        return '待评估';
    }
  }

  Future<String?> _inspectImage(XFile file) async {
    try {
      final bytes = await file.readAsBytes();
      if (bytes.length < 12 * 1024) {
        return '图片太小，请上传更清晰的图片';
      }

      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final width = frame.image.width;
      final height = frame.image.height;
      if (width < 256 || height < 256) {
        return '图片分辨率过低，请上传至少 256px 的清晰图片';
      }

      // 经验性预检：衣服图若明显像人物竖图，优先提醒用户改成商品图。
      final isPortrait = height > width * 1.15;
      final isLargeEnough = bytes.length > 80 * 1024;
      if (file == _garmentImage && isPortrait && isLargeEnough) {
        final signals = await _estimateGarmentPhotoSignals(frame.image);
        // 仅在强信号下阻断，避免把平铺衣服图误判成人物图。
        if (signals.veryLikelyPerson) {
          return '衣服图疑似人物照，请改用无模特白底商品图';
        }
      }
    } catch (_) {
      // 预检失败不阻断主流程，由后端继续兜底校验。
    }
    return null;
  }

  Future<_GarmentPhotoSignals> _estimateGarmentPhotoSignals(
      ui.Image image) async {
    final byteData = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (byteData == null) return const _GarmentPhotoSignals();

    final rgba = byteData.buffer.asUint8List();
    final pixelCount = image.width * image.height;
    if (pixelCount <= 0) return const _GarmentPhotoSignals();

    final rawStep = (pixelCount / 12000).ceil();
    final step = rawStep < 1
        ? 1
        : rawStep > 32
            ? 32
            : rawStep;

    var sampled = 0;
    var skinLike = 0;
    var brightBg = 0;

    for (var i = 0; i < pixelCount; i += step) {
      final idx = i * 4;
      if (idx + 3 >= rgba.length) break;
      final a = rgba[idx + 3];
      if (a < 24) continue;

      final r = rgba[idx];
      final g = rgba[idx + 1];
      final b = rgba[idx + 2];

      sampled++;

      final maxV = r > g ? (r > b ? r : b) : (g > b ? g : b);
      final minV = r < g ? (r < b ? r : b) : (g < b ? g : b);
      final cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
      final cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
      final likelySkin = r > 95 &&
          g > 40 &&
          b > 20 &&
          (maxV - minV) > 15 &&
          (r - g).abs() > 15 &&
          r > g &&
          r > b &&
          g > b &&
          cb >= 92 &&
          cb <= 128 &&
          cr >= 138 &&
          cr <= 176;
      if (likelySkin) {
        skinLike++;
      }
      if (r > 230 && g > 230 && b > 230) {
        brightBg++;
      }
    }

    if (sampled == 0) return const _GarmentPhotoSignals();
    return _GarmentPhotoSignals(
      skinRatio: skinLike / sampled,
      brightBgRatio: brightBg / sampled,
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return Scaffold(
      backgroundColor: palette.background,
      appBar: AppBar(
        title: const Text('虚拟试衣'),
        backgroundColor: palette.background,
        surfaceTintColor: Colors.transparent,
        foregroundColor: palette.textTitle,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    palette.surface.withValues(alpha: 0.92),
                    palette.primary.withValues(alpha: 0.06),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(12),
                border:
                    Border.all(color: palette.divider.withValues(alpha: 0.85)),
                boxShadow: [
                  BoxShadow(
                    color: palette.primary.withValues(alpha: 0.06),
                    blurRadius: 20,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.info_outline, size: 18, color: palette.accent),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '请上传无模特的衣服图，否则效果会出现重影。'
                          '尽量使用白底或平铺商品主图；含人像的商品图会被拒绝。未加载 AI 扩散模型时，后端会用去背景+粘贴合成。',
                          style: TextStyle(
                            fontSize: 12,
                            color: palette.textBody,
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: OutlinedButton.icon(
                            onPressed: _showTryOnTips,
                            style: OutlinedButton.styleFrom(
                              visualDensity: VisualDensity.compact,
                              foregroundColor: palette.primary,
                              side: BorderSide(
                                color: palette.primary.withValues(alpha: 0.35),
                              ),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(999),
                              ),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 8,
                              ),
                            ),
                            icon: const Icon(
                              Icons.tips_and_updates_outlined,
                              size: 16,
                            ),
                            label: const Text(
                              '查看建议图样',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: palette.surface,
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
                      Icon(Icons.rule_outlined,
                          size: 18, color: palette.primary),
                      const SizedBox(width: 8),
                      Text(
                        '上传标准',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: palette.textTitle,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _StandardChip(
                        label: '无模特',
                        icon: Icons.person_off_outlined,
                        color: Colors.green,
                      ),
                      _StandardChip(
                        label: '白底/纯背景',
                        icon: Icons.wallpaper_outlined,
                        color: Colors.blue,
                      ),
                      _StandardChip(
                        label: '主体清晰',
                        icon: Icons.high_quality_outlined,
                        color: Colors.orange,
                      ),
                      _StandardChip(
                        label: '分辨率足够',
                        icon: Icons.photo_size_select_actual_outlined,
                        color: Colors.purple,
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '优先上传商品详情页主图，不要用模特图、海报拼图或分辨率过低的图片。',
                    style: TextStyle(
                      fontSize: 12,
                      color: palette.textBody,
                      height: 1.35,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Row(
                    children: [
                      Expanded(
                        child: _ExampleTile(
                          label: '推荐示例',
                          text: '白底平铺商品图\n无模特\n主体完整',
                          icon: Icons.check_circle,
                          color: Colors.green,
                        ),
                      ),
                      SizedBox(width: 10),
                      Expanded(
                        child: _ExampleTile(
                          label: '不推荐示例',
                          text: '模特海报图\n多人合照\n低分辨率',
                          icon: Icons.cancel,
                          color: Colors.redAccent,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // 上传区
            Row(
              children: [
                Expanded(
                  child: _PickBox(
                    label: '衣服图',
                    image: _garmentImage,
                    onTap: _pickGarment,
                    onClear: () => setState(() {
                      _garmentImage = null;
                      _garmentImage2 = null;
                      _garmentQualityHint = null;
                      _resetPrecheckPanel();
                    }),
                    palette: palette,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: _PickBox(
                    label: _garmentCategory == _GarmentCategoryChoice.bottom
                        ? '人物照（必填，完整全身）'
                        : '人物照（必填，建议全身）',
                    image: _personFront,
                    onTap: _pickPerson,
                    onClear: () => setState(() {
                      _personFront = null;
                      _resetPrecheckPanel();
                    }),
                    palette: palette,
                  ),
                ),
              ],
            ),
            if (_garmentCategory == _GarmentCategoryChoice.bottom) ...[
              const SizedBox(height: 8),
              Text(
                '请上传完整站立全身照，确保腰部、双腿、脚踝清晰可见。',
                style: TextStyle(
                  fontSize: 12,
                  color: palette.textBody.withValues(alpha: 0.85),
                ),
              ),
            ],
            if (_garmentCategory == _GarmentCategoryChoice.outfit) ...[
              const SizedBox(height: 12),
              _PickBox(
                label: '第二件（下装/裙装）',
                image: _garmentImage2,
                onTap: _pickGarment2,
                onClear: () => setState(() {
                  _garmentImage2 = null;
                  _resetPrecheckPanel();
                }),
                palette: palette,
              ),
            ],
            if (_garmentQualityHint != null) ...[
              const SizedBox(height: 10),
              _QualityBadge(
                title: _garmentQualityTitle(_garmentQualityHint),
                message: _garmentQualityHint!,
                color: _garmentQualityColor(_garmentQualityHint, palette),
              ),
            ],
            if (_standardizedGarmentUrl != null ||
                (_garmentCategory == _GarmentCategoryChoice.outfit &&
                    _standardizedGarmentUrl2 != null)) ...[
              const SizedBox(height: 10),
              _StandardizedPreviewCard(
                primaryUrl: _standardizedGarmentUrl,
                secondaryUrl: _standardizedGarmentUrl2,
                palette: palette,
              ),
            ],
            if (_precheckMessage != null || _precheckScores.isNotEmpty) ...[
              const SizedBox(height: 10),
              _PrecheckResultCard(
                passed: _precheckPassed,
                message: _precheckMessage,
                hint: _precheckHint,
                errorCode: _precheckErrorCode,
                scores: _precheckScores,
                thresholds: _precheckThresholds,
                source: _precheckSource,
                palette: palette,
              ),
            ],
            const SizedBox(height: 14),
            Text(
              '衣物品类',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: palette.textTitle,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _GarmentCategoryChoice.values.map((c) {
                final selected = _garmentCategory == c;
                return ChoiceChip(
                  label: Text(c.label),
                  selected: selected,
                  onSelected: (_) => setState(() {
                    _garmentCategory = c;
                    if (_garmentCategory != _GarmentCategoryChoice.outfit) {
                      _garmentImage2 = null;
                    }
                    // Pants must use CatVTON high-quality modes, not paste.
                    if (_garmentCategory == _GarmentCategoryChoice.bottom) {
                      _qualityMode = _TryOnQualityMode.professional;
                    }
                    _resetPrecheckPanel();
                  }),
                  selectedColor: palette.primary.withValues(alpha: 0.22),
                  labelStyle: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: selected ? palette.primary : palette.textBody,
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 14),
            Text(
              '效果模式',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: palette.textTitle,
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _TryOnQualityMode.values.map((m) {
                final selected = _qualityMode == m;
                return ChoiceChip(
                  label: Text(m.label),
                  selected: selected,
                  onSelected: (_) => setState(() {
                    _qualityMode = m;
                    _resetPrecheckPanel();
                  }),
                  selectedColor: palette.primary.withValues(alpha: 0.22),
                  labelStyle: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: selected ? palette.primary : palette.textBody,
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 8),
            Text(
              _qualityMode.description,
              style: TextStyle(
                  fontSize: 12, height: 1.35, color: palette.textBody),
            ),
            // 细节保真特别提示
            if (_qualityMode == _TryOnQualityMode.professional) ...[
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.purple.withValues(alpha: 0.15),
                      Colors.blue.withValues(alpha: 0.10),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.purple.withValues(alpha: 0.3),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.auto_fix_high,
                            size: 16, color: Colors.purple.shade700),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'CatVTON 深度学习 + 颜色保真增强',
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.purple.shade700,
                              height: 1.3,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'AI 重新生成贴合光影，同时用原始衣服图的颜色修正图案细节',
                      style: TextStyle(
                        fontSize: 10,
                        color: Colors.purple.shade600,
                        height: 1.2,
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // 混合模式特别提示
            if (_qualityMode == _TryOnQualityMode.hybrid) ...[
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.teal.withValues(alpha: 0.15),
                      Colors.green.withValues(alpha: 0.10),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.teal.withValues(alpha: 0.3),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.layers_outlined,
                            size: 16, color: Colors.teal.shade700),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            '混合模式原理：Warp保真 + CatVTON光影增强',
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.teal.shade700,
                              height: 1.3,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '100%保留衣服原始图案/颜色（来自Warp）+ AI光影/褶皱（来自CatVTON），'
                      '两者叠加得到自然贴合效果',
                      style: TextStyle(
                        fontSize: 10,
                        color: Colors.teal.shade600,
                        height: 1.2,
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // 标准图粘贴模式特别提示
            if (_qualityMode == _TryOnQualityMode.paste) ...[
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.orange.withValues(alpha: 0.15),
                      Colors.amber.withValues(alpha: 0.10),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.orange.withValues(alpha: 0.3),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.content_paste,
                            size: 16, color: Colors.orange.shade700),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            '标准图粘贴模式原理：自动旋转 + 身体比例缩放 + 几何贴合',
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.orange.shade700,
                              height: 1.3,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '自动检测平铺图的拍摄方向并旋转，按人物肩宽等比缩放后贴合，'
                      '跳过AI深度学习，处理最快',
                      style: TextStyle(
                        fontSize: 10,
                        color: Colors.orange.shade600,
                        height: 1.2,
                      ),
                    ),
                  ],
                ),
              ),
            ],

            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.amber.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: Colors.amber.withValues(alpha: 0.35),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.warning_amber_rounded,
                        size: 18,
                        color: Colors.amber.shade900,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '试裤子、裙子时请点选对应品类；仅用「自动」可能路由不准。',
                          style: TextStyle(
                            fontSize: 12,
                            height: 1.35,
                            color: palette.textBody,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '人物图请尽量「全身、正面」；试裤子需拍到腿部。若人物已穿连衣裙等一体式服装，再试裤子容易与模型假设冲突，建议换简洁上下装照片。',
                    style: TextStyle(
                      fontSize: 12,
                      height: 1.35,
                      color: palette.textBody,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // 生成按钮
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: ((_garmentImage != null ||
                            (_standardizedGarmentUrl?.trim().isNotEmpty ??
                                false) ||
                            _prefilledGarmentId != null) &&
                        _personFront != null &&
                        !_loading)
                    ? _generate
                    : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: palette.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: palette.divider,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(26)),
                ),
                icon: _loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.auto_fix_high),
                label: Text(_loading ? '正在生成试衣图…' : '生成虚拟试衣',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 28),

            // 结果展示
            if (_results.isNotEmpty) ...[
              const Text(
                '虚拟试衣效果',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              _TryOnCarousel(
                urls: _results,
                palette: palette,
                pageController: _pageCtrl,
                currentIndex: _currentIndex,
                onIndexChanged: (i) => setState(() => _currentIndex = i),
                aspectRatioCache: _aspectRatioCache,
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _saveCurrentResult,
                icon: const Icon(Icons.download_outlined),
                label: Text(kIsWeb ? '打开试衣图' : '保存到相册'),
              ),
              const SizedBox(height: 12),
              if (_results.length > 1) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: List.generate(_results.length, (i) {
                    return AnimatedContainer(
                      duration: const Duration(milliseconds: 250),
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      width: i == _currentIndex ? 24 : 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: i == _currentIndex
                            ? palette.primary
                            : palette.divider,
                        borderRadius: _carouselDotRadius,
                      ),
                    );
                  }),
                ),
                const SizedBox(height: 8),
              ],
              if (_results.length > 1)
                Text(
                  '← 左右滑动切换 →',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: palette.textBody),
                ),
            ],
          ],
        ),
      ),
    );
  }

  // (placeholder moved into _TryOnCarousel for better layout control)
}

enum _TryOnQualityLevel { good, medium, poor, unknown }

class _GarmentPhotoSignals {
  final double skinRatio;
  final double brightBgRatio;

  const _GarmentPhotoSignals({
    this.skinRatio = 0,
    this.brightBgRatio = 0,
  });

  bool get likelyPerson => skinRatio >= 0.28 && brightBgRatio <= 0.88;
  bool get veryLikelyPerson => skinRatio >= 0.48 && brightBgRatio <= 0.84;
}

class _StandardChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;

  const _StandardChip({
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

class _QualityBadge extends StatelessWidget {
  final String title;
  final String message;
  final Color color;

  const _QualityBadge({
    required this.title,
    required this.message,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            color.withValues(alpha: 0.12),
            color.withValues(alpha: 0.04),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.bolt, size: 14, color: color),
                const SizedBox(width: 4),
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    color: color,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 12,
                height: 1.35,
                color: Colors.black.withValues(alpha: 0.72),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PrecheckResultCard extends StatelessWidget {
  final bool? passed;
  final String? message;
  final String? hint;
  final String? errorCode;
  final Map<String, double> scores;
  final Map<String, double> thresholds;
  final String? source;
  final Palette palette;

  const _PrecheckResultCard({
    required this.passed,
    required this.message,
    required this.hint,
    required this.errorCode,
    required this.scores,
    required this.thresholds,
    required this.source,
    required this.palette,
  });

  String _label(String key) {
    switch (key) {
      case 'full_body_score':
      case 'full_body':
        return '全身可见';
      case 'leg_visibility_score':
      case 'leg_visibility':
        return '腿部可见';
      case 'front_pose_score':
      case 'front_pose':
        return '正面姿态';
      case 'garment_front_score':
      case 'garment_front':
        return '商品图正面度';
      default:
        return key;
    }
  }

  String? _mappedFixSuggestion(String? code) {
    switch ((code ?? '').trim()) {
      case 'TRYON_V2_PERSON_NOT_FULL_BODY':
        return '请上传完整站立照，确保头顶到脚部全部入镜。';
      case 'TRYON_V2_PERSON_LEG_NOT_VISIBLE':
        return '请避免遮挡腿部，拍摄时退后并保证下半身清晰。';
      case 'TRYON_V2_PERSON_NOT_FRONT_VIEW':
        return '请改用正面站姿照片，避免侧身或大角度转身。';
      case 'TRYON_V2_GARMENT_NOT_FRONT_VIEW':
        return '请使用正面商品图，主体完整、背景干净。';
      case 'TRYON_V2_UNSUPPORTED_CATEGORY':
        return '当前仅支持下装，请将品类切到下装或裙装后再试。';
      case 'TRYON_GARMENT_CONTAINS_MODEL':
        return '请使用无模特商品图，避免人物脸部或上身出现在衣物图中。';
      case 'LOCAL_GARMENT_PRECHECK_FAILED':
        return '请替换为清晰的无模特商品图，建议白底且主体占比更大。';
      case 'LOCAL_PERSON_PRECHECK_FAILED':
        return '请上传清晰全身正面照，保证腿部可见且分辨率足够。';
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final scoreKeys = <String>[
      'full_body_score',
      'leg_visibility_score',
      'front_pose_score',
      'garment_front_score',
    ];
    final scoreRows = <MapEntry<String, double>>[];
    for (final k in scoreKeys) {
      final v = scores[k];
      if (v != null) scoreRows.add(MapEntry(k, v));
    }

    final Color tone = passed == true
        ? Colors.green
        : passed == false
            ? Colors.redAccent
            : palette.primary;
    final String title = passed == true
        ? '预检通过'
        : passed == false
            ? '预检未通过'
            : '预检状态';
    final mappedHint = _mappedFixSuggestion(errorCode);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            tone.withValues(alpha: 0.12),
            tone.withValues(alpha: 0.03),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: tone.withValues(alpha: 0.34)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                passed == true
                    ? Icons.verified_outlined
                    : passed == false
                        ? Icons.gpp_bad_outlined
                        : Icons.info_outline,
                size: 16,
                color: tone,
              ),
              const SizedBox(width: 6),
              Text(
                title,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: tone,
                ),
              ),
              if (source != null && source!.trim().isNotEmpty) ...[
                const SizedBox(width: 8),
                Text(
                  '来源: $source',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.black.withValues(alpha: 0.52),
                  ),
                ),
              ],
            ],
          ),
          if (message != null && message!.trim().isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              message!,
              style: TextStyle(
                fontSize: 12,
                color: Colors.black.withValues(alpha: 0.74),
                height: 1.35,
              ),
            ),
          ],
          if (errorCode != null && errorCode!.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            SelectableText(
              '错误码：$errorCode',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: Colors.black.withValues(alpha: 0.62),
              ),
            ),
          ],
          if (hint != null && hint!.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '建议：$hint',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: Colors.black.withValues(alpha: 0.72),
              ),
            ),
          ],
          if ((hint == null || hint!.trim().isEmpty) &&
              mappedHint != null &&
              mappedHint.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '建议：$mappedHint',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: Colors.black.withValues(alpha: 0.72),
              ),
            ),
          ],
          if (scoreRows.isNotEmpty) ...[
            const SizedBox(height: 10),
            ...scoreRows.map((entry) {
              final normalizedThresholdKey = entry.key.replaceAll('_score', '');
              final threshold = thresholds[normalizedThresholdKey];
              final value = entry.value;
              final pass = threshold == null ? null : value >= threshold;
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _label(entry.key),
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.black.withValues(alpha: 0.7),
                        ),
                      ),
                    ),
                    Text(
                      value.toStringAsFixed(2),
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: pass == true
                            ? Colors.green
                            : pass == false
                                ? Colors.redAccent
                                : Colors.black.withValues(alpha: 0.72),
                      ),
                    ),
                    if (threshold != null) ...[
                      const SizedBox(width: 6),
                      Text(
                        '/ ${threshold.toStringAsFixed(2)}',
                        style: TextStyle(
                          fontSize: 11,
                          color: Colors.black.withValues(alpha: 0.45),
                        ),
                      ),
                    ],
                  ],
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}

class _ExampleTile extends StatelessWidget {
  final String label;
  final String text;
  final IconData icon;
  final Color color;

  const _ExampleTile({
    required this.label,
    required this.text,
    required this.icon,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            text,
            style: TextStyle(
              fontSize: 11,
              height: 1.45,
              color: color.withValues(alpha: 0.88),
            ),
          ),
        ],
      ),
    );
  }
}

class _TipRow extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String text;

  const _TipRow({
    required this.icon,
    required this.color,
    required this.title,
    required this.text,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 8),
        Expanded(
          child: RichText(
            text: TextSpan(
              style: DefaultTextStyle.of(context)
                  .style
                  .copyWith(fontSize: 13, height: 1.4),
              children: [
                TextSpan(
                  text: '$title：',
                  style: TextStyle(color: color, fontWeight: FontWeight.w700),
                ),
                TextSpan(text: text),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PickBox extends StatelessWidget {
  final String label;
  final XFile? image;
  final VoidCallback onTap;
  final VoidCallback? onClear;
  final Palette palette;

  const _PickBox({
    required this.label,
    required this.image,
    required this.onTap,
    required this.onClear,
    required this.palette,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        children: [
          Container(
            height: 120,
            decoration: BoxDecoration(
              color: palette.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: palette.divider),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.04),
                  blurRadius: 14,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: image != null
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(15),
                    child: PlatformImage(
                      xfile: image,
                      fit: BoxFit.cover,
                      errorWidget: Container(
                        color: palette.primary.withValues(alpha: 0.1),
                        child: Icon(Icons.broken_image, color: palette.primary),
                      ),
                    ),
                  )
                : Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.add_photo_alternate_outlined,
                          size: 32, color: palette.textBody),
                      const SizedBox(height: 8),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: Text(
                          label,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: palette.textBody,
                              fontSize: 12,
                              height: 1.2),
                        ),
                      ),
                    ],
                  ),
          ),
          if (image != null && onClear != null)
            Positioned(
              top: 6,
              right: 6,
              child: GestureDetector(
                onTap: onClear,
                child: Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.close, size: 16, color: Colors.white),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _StandardizedPreviewCard extends StatelessWidget {
  const _StandardizedPreviewCard({
    required this.primaryUrl,
    required this.secondaryUrl,
    required this.palette,
  });

  final String? primaryUrl;
  final String? secondaryUrl;
  final Palette palette;

  void _open(BuildContext context, String url) {
    showDialog<void>(
      context: context,
      builder: (ctx) {
        final auth = ctx.read<AuthProvider>();
        final base = auth.apiClient.baseUrl;
        final resolved = resolveGarmentImageUrl(url, base) ?? url;
        return Dialog(
          insetPadding: const EdgeInsets.all(16),
          child: AspectRatio(
            aspectRatio: 1,
            child: InteractiveViewer(
              minScale: 0.6,
              maxScale: 4,
              child: PlatformImage(
                networkUrl: resolved,
                fit: BoxFit.contain,
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthProvider>();
    final base = auth.apiClient.baseUrl;
    final p = primaryUrl;
    final s = secondaryUrl;
    final rp = p != null ? (resolveGarmentImageUrl(p, base) ?? p) : null;
    final rs = s != null ? (resolveGarmentImageUrl(s, base) ?? s) : null;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: palette.primary.withValues(alpha: 0.20)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_fix_high, size: 16, color: palette.primary),
              const SizedBox(width: 8),
              Text(
                '白底标准图（预处理输出）',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: palette.textTitle,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              if (rp != null)
                _StandardizedThumb(
                  label: '衣服图',
                  url: rp,
                  palette: palette,
                  onTap: () => _open(context, p!),
                ),
              if (rs != null)
                _StandardizedThumb(
                  label: '第二件',
                  url: rs,
                  palette: palette,
                  onTap: () => _open(context, s!),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '用于确认接口实际收到的“无背景白底主体图”。若仍包含手/文字/大片背景，建议换图或裁剪。',
            style:
                TextStyle(fontSize: 11, height: 1.3, color: palette.textBody),
          ),
        ],
      ),
    );
  }
}

class _StandardizedThumb extends StatelessWidget {
  const _StandardizedThumb({
    required this.label,
    required this.url,
    required this.palette,
    required this.onTap,
  });

  final String label;
  final String url;
  final Palette palette;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 132,
        height: 132,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: palette.divider),
        ),
        child: Column(
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(12)),
                child: PlatformImage(networkUrl: url, fit: BoxFit.cover),
              ),
            ),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: palette.surface,
                borderRadius:
                    const BorderRadius.vertical(bottom: Radius.circular(12)),
              ),
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: palette.textBody,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TryOnCarousel extends StatelessWidget {
  final List<String> urls;
  final Palette palette;
  final PageController pageController;
  final int currentIndex;
  final ValueChanged<int> onIndexChanged;
  final Map<String, double> aspectRatioCache;

  const _TryOnCarousel({
    required this.urls,
    required this.palette,
    required this.pageController,
    required this.currentIndex,
    required this.onIndexChanged,
    required this.aspectRatioCache,
  });

  static const _labels = ['正面', '侧面', '背面'];

  @override
  Widget build(BuildContext context) {
    final angleLabel = currentIndex < _labels.length
        ? _labels[currentIndex]
        : '视角 ${currentIndex + 1}';
    final url = currentIndex < urls.length ? urls[currentIndex] : '';
    final ratio = (url.isNotEmpty ? aspectRatioCache[url] : null) ?? (3 / 4);
    final placeholder = _placeholder(angleLabel);

    return GestureDetector(
      onTap: () {
        if (urls.isEmpty) return;
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => _TryOnFullscreenGallery(
              urls: urls,
              initialIndex: currentIndex,
              palette: palette,
              aspectRatioCache: aspectRatioCache,
            ),
          ),
        );
      },
      child: Center(
        child: AspectRatio(
          aspectRatio: ratio,
          child: Card(
            elevation: 0,
            margin: EdgeInsets.zero,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(color: palette.divider),
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(20),
                  child: _TryOnNetworkImage(
                    url: url,
                    fit: BoxFit.contain,
                    palette: palette,
                    onAspectRatio: (r) {
                      if (url.isEmpty) return;
                      aspectRatioCache[url] = r;
                    },
                    placeholder: placeholder,
                  ),
                ),
                Positioned(
                  bottom: 12,
                  right: 12,
                  child: _AngleChip(label: angleLabel, color: palette.primary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _placeholder(String label) {
    return ColoredBox(
      color: palette.surface,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.threed_rotation,
                size: 64, color: palette.primary.withValues(alpha: 0.35)),
            const SizedBox(height: 10),
            Text(label,
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: palette.textTitle)),
            const SizedBox(height: 2),
            Text('点击生成多角度试衣图',
                style: TextStyle(fontSize: 12, color: palette.textBody)),
          ],
        ),
      ),
    );
  }
}

class _AngleChip extends StatelessWidget {
  final String label;
  final Color color;

  const _AngleChip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.14),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Text(
        label,
        style: const TextStyle(
            color: Colors.white, fontWeight: FontWeight.w800, fontSize: 12),
      ),
    );
  }
}

class _TryOnNetworkImage extends StatefulWidget {
  final String url;
  final BoxFit fit;
  final Palette palette;
  final Widget placeholder;
  final ValueChanged<double> onAspectRatio;

  const _TryOnNetworkImage({
    required this.url,
    required this.fit,
    required this.palette,
    required this.placeholder,
    required this.onAspectRatio,
  });

  @override
  State<_TryOnNetworkImage> createState() => _TryOnNetworkImageState();
}

class _TryOnNetworkImageState extends State<_TryOnNetworkImage> {
  ImageStream? _stream;
  ImageStreamListener? _listener;

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  @override
  void didUpdateWidget(covariant _TryOnNetworkImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) _resolve();
  }

  void _resolve() {
    _detach();
    if (widget.url.isEmpty) return;
    final provider = NetworkImage(widget.url);
    final stream = provider.resolve(const ImageConfiguration());
    _stream = stream;
    _listener = ImageStreamListener((info, _) {
      final w = info.image.width.toDouble();
      final h = info.image.height.toDouble();
      if (w > 0 && h > 0) widget.onAspectRatio(w / h);
    });
    stream.addListener(_listener!);
  }

  void _detach() {
    if (_stream != null && _listener != null) {
      _stream!.removeListener(_listener!);
    }
    _stream = null;
    _listener = null;
  }

  @override
  void dispose() {
    _detach();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.url.isEmpty) return widget.placeholder;
    return ColoredBox(
      color: widget.palette.surface,
      child: Image.network(
        widget.url,
        fit: widget.fit,
        alignment: Alignment.center,
        errorBuilder: (_, __, ___) => widget.placeholder,
        loadingBuilder: (ctx, child, progress) {
          if (progress == null) return child;
          return Center(
            child: SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: widget.palette.primary,
                value: progress.expectedTotalBytes == null
                    ? null
                    : progress.cumulativeBytesLoaded /
                        (progress.expectedTotalBytes ?? 1),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _TryOnFullscreenGallery extends StatefulWidget {
  final List<String> urls;
  final int initialIndex;
  final Palette palette;
  final Map<String, double> aspectRatioCache;

  const _TryOnFullscreenGallery({
    required this.urls,
    required this.initialIndex,
    required this.palette,
    required this.aspectRatioCache,
  });

  @override
  State<_TryOnFullscreenGallery> createState() =>
      _TryOnFullscreenGalleryState();
}

class _TryOnFullscreenGalleryState extends State<_TryOnFullscreenGallery> {
  late final PageController _ctrl =
      PageController(initialPage: widget.initialIndex);
  int _index = 0;
  static const _labels = ['正面', '侧面', '背面'];

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex;
  }

  @override
  Widget build(BuildContext context) {
    final palette = widget.palette;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('试衣预览'),
      ),
      body: Stack(
        children: [
          PageView.builder(
            controller: _ctrl,
            itemCount: widget.urls.length,
            onPageChanged: (i) => setState(() => _index = i),
            itemBuilder: (_, i) {
              final url = widget.urls[i];
              return InteractiveViewer(
                minScale: 1,
                maxScale: 4,
                child: Center(
                  child: Image.network(
                    url,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Center(
                      child:
                          Text('加载失败', style: TextStyle(color: Colors.white70)),
                    ),
                  ),
                ),
              );
            },
          ),
          Positioned(
            bottom: 16,
            right: 16,
            child: _AngleChip(
              label: _index < _labels.length
                  ? _labels[_index]
                  : '视角 ${_index + 1}',
              color: palette.primary,
            ),
          ),
        ],
      ),
    );
  }
}
