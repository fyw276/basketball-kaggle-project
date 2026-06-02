import 'package:city_pickers/city_pickers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/utils/app_snackbar.dart' show showAppSnackBar;
import 'smart_outfit_cache.dart';
import 'smart_outfit_geo_weather.dart';

enum SmartOutfitGenerateKind {
  success,
  needImage,
  needReferenceCategory,
  notAuthenticated,
  credentialInvalid,
  apiError,
  emptyOutfits,
}

/// Outcome of [SmartOutfitController.generateSmartOutfit] (upload + generate API).
class SmartOutfitGenerateResult {
  final SmartOutfitGenerateKind kind;
  final List<Map<String, dynamic>> outfits;
  final Object? error;
  final bool connectionRetrySuggested;

  const SmartOutfitGenerateResult._({
    required this.kind,
    this.outfits = const [],
    this.error,
    this.connectionRetrySuggested = false,
  });

  bool get isSuccess => kind == SmartOutfitGenerateKind.success;

  factory SmartOutfitGenerateResult.success(List<Map<String, dynamic>> items) {
    return SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.success,
      outfits: items,
    );
  }

  static SmartOutfitGenerateResult needImage() {
    return const SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.needImage,
    );
  }

  static SmartOutfitGenerateResult needReferenceCategory() {
    return const SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.needReferenceCategory,
    );
  }

  static SmartOutfitGenerateResult notAuthenticated() {
    return const SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.notAuthenticated,
    );
  }

  static SmartOutfitGenerateResult credentialInvalid() {
    return const SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.credentialInvalid,
    );
  }

  static SmartOutfitGenerateResult emptyOutfits() {
    return const SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.emptyOutfits,
    );
  }

  factory SmartOutfitGenerateResult.apiError(
    Object e, {
    bool connectionRetrySuggested = false,
  }) {
    return SmartOutfitGenerateResult._(
      kind: SmartOutfitGenerateKind.apiError,
      error: e,
      connectionRetrySuggested: connectionRetrySuggested,
    );
  }
}

/// 智能穿搭会话：天气/定位 + 参考图 + 生成（需 UI 处显式传入 [BuildContext] 做选城、SnackBar）。
class SmartOutfitController extends ChangeNotifier {
  final List<XFile> _images = [];

  List<XFile> get images => _images;

  String? imageUrl;
  String? referenceCategory;
  String? referenceColorName;
  Map<String, dynamic> referenceRecognition = const {};
  bool referenceUploading = false;
  List<Map<String, dynamic>> outfits = [];
  int regenIndex = 0;
  bool generating = false;
  bool oneTapBusy = false;

  bool get needsReferenceCategoryConfirmation =>
      referenceRecognition['reference_low_confidence'] == true &&
      (referenceCategory == null || referenceCategory!.trim().isEmpty);

  // —— 天气 / 定位（与生成共用）——
  String cityShort = '';
  Map<String, String> addressParts = const {};
  String fullAddressLine = '';
  String displayAddress = '';
  String weather = '晴';
  double temp = 20;
  bool weatherLoading = true;
  bool weatherFallback = false;

  int _weatherSeq = 0;
  bool weatherRequestInFlight = false;

  String get locationForApi {
    return fullAddressLine.trim().isNotEmpty
        ? fullAddressLine.trim()
        : displayAddress.trim().isNotEmpty
            ? displayAddress.trim()
            : cityShort.trim();
  }

  static bool isCredentialInvalid(Object? error) {
    final s = (error?.toString() ?? '').toLowerCase();
    return s.contains('could not validate credentials') ||
        s.contains('not authenticated') ||
        s.contains('401');
  }

  static bool _suggestConnectionRetry(Object? e) {
    final s = (e?.toString() ?? '');
    return s.contains('无法连接') ||
        s.contains('网络') ||
        s.contains('SocketException') ||
        s.contains('Failed host lookup') ||
        s.contains('ClientException');
  }

  static Future<void> waitForAuthReady(BuildContext context) async {
    if (!context.mounted) return;
    var auth = context.read<AuthProvider>();
    if (auth.isInitialized) return;
    const step = Duration(milliseconds: 16);
    for (var i = 0; i < 200; i++) {
      await Future.delayed(step);
      if (!context.mounted) return;
      auth = context.read<AuthProvider>();
      if (auth.isInitialized) return;
    }
  }

  void _persistWeatherToPrefs() {
    SmartOutfitWeatherCache.persist(
      fullAddressLine: fullAddressLine,
      cityShort: cityShort,
      weather: weather,
      temp: temp,
      weatherFallback: weatherFallback,
    );
  }

  void _applyWeatherFromSnapshot(SmartOutfitWeatherSnapshot snap) {
    fullAddressLine = snap.fullAddressLine;
    displayAddress = snap.displayAddress;
    cityShort = snap.cityShort;
    weather = snap.weather;
    temp = snap.temp;
    weatherFallback = snap.weatherFallback;
    weatherLoading = false;
  }

  void applyWeatherPayload(Map<String, dynamic> r, {required bool fallback}) {
    final addr = Map<String, dynamic>.from(r['address'] ?? const {});
    final p = addr['province']?.toString().trim() ?? '';
    final c = addr['city']?.toString().trim() ?? '';
    final d = addr['district']?.toString().trim() ?? '';
    final s = addr['street']?.toString().trim() ?? '';
    final full = addr['full_address']?.toString().trim() ??
        r['full_address']?.toString().trim() ??
        '';
    final disp = addr['display_address']?.toString().trim() ??
        r['display_address']?.toString().trim() ??
        full;
    final city = c.isNotEmpty ? c : r['city']?.toString().trim();
    if (kDebugMode) {
      final gs = r['geocode_source']?.toString();
      final ge = r['geocode_error']?.toString();
      if ((gs != null && gs.isNotEmpty) || (ge != null && ge.isNotEmpty)) {
        debugPrint(
          '[smart_outfit weather] geocode_source=$gs geocode_error=$ge',
        );
      }
    }
    addressParts = {
      if (p.isNotEmpty) 'province': p,
      if (c.isNotEmpty) 'city': c,
      if (d.isNotEmpty) 'district': d,
      if (s.isNotEmpty) 'street': s,
    };
    fullAddressLine = full.isNotEmpty ? full : disp;
    displayAddress = disp;
    cityShort = city != null && city.isNotEmpty ? city : '';
    weather = r['weather']?.toString() ?? '晴';
    temp = (r['temperature'] as num?)?.toDouble() ?? 20;
    weatherFallback = fallback;
    weatherLoading = false;
    notifyListeners();
    WidgetsBinding.instance
        .addPostFrameCallback((_) => _persistWeatherToPrefs());
  }

  /// 读本地缓存后拉 GPS 天气（[onCredentialInvalid] 在401 时由页面处理登出）。
  Future<void> restoreCacheThenFetchGps(
    BuildContext context, {
    required void Function() onCredentialInvalid,
  }) async {
    final snap = await SmartOutfitWeatherCache.restore();
    if (snap != null) {
      _applyWeatherFromSnapshot(snap);
      notifyListeners();
    }
    if (!context.mounted) return;
    await loadWeatherFromGps(
      context,
      onCredentialInvalid: onCredentialInvalid,
    );
  }

  Future<void> reloadGpsWeather(
    BuildContext context, {
    required void Function() onCredentialInvalid,
  }) async {
    if (weatherRequestInFlight) return;
    fullAddressLine = '';
    displayAddress = '';
    cityShort = '';
    notifyListeners();
    await loadWeatherFromGps(
      context,
      onCredentialInvalid: onCredentialInvalid,
    );
  }

  Future<void> loadWeatherFromGps(
    BuildContext context, {
    required void Function() onCredentialInvalid,
  }) async {
    if (weatherRequestInFlight) return;
    await waitForAuthReady(context);
    if (!context.mounted) return;
    final auth0 = context.read<AuthProvider>();
    if (!auth0.isAuthenticated) {
      weatherLoading = false;
      notifyListeners();
      return;
    }

    for (var i = 0; i < 80; i++) {
      if (auth0.token != null && auth0.token!.isNotEmpty) break;
      await Future.delayed(const Duration(milliseconds: 25));
      if (!context.mounted) return;
    }

    final prevFallback = weatherFallback;
    final prevFull = fullAddressLine;
    final prevDisp = displayAddress;
    final prevCity = cityShort;
    final prevWeather = weather;
    final prevTemp = temp;

    weatherRequestInFlight = true;
    final seq = ++_weatherSeq;
    final api = context.read<AuthProvider>().apiClient;
    final palette = context.read<ThemeProvider>().palette;

    try {
      if (!context.mounted) return;
      weatherLoading = true;
      weatherFallback = false;
      notifyListeners();

      var serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        throw StateError('location_service_disabled');
      }

      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.deniedForever) {
        if (!context.mounted || seq != _weatherSeq) return;
        weatherLoading = false;
        notifyListeners();
        await pickManualCityWeather(context, seq: seq);
        return;
      }

      final pos = await SmartOutfitGeo.currentPositionWithRetry();
      if (context.mounted && SmartOutfitGeo.poorAccuracy(pos)) {
        showAppSnackBar(
          context,
          '当前位置精度较低（约 ${pos.accuracy.toStringAsFixed(0)} m）。'
          '请在浏览器地址栏左侧「位置」权限中选择“精确位置”，或改用「手动选择地址」。',
          backgroundColor: palette.textBody,
        );
      }
      final r = await api.getSmartOutfitWeather(pos.latitude, pos.longitude);
      if (r['error'] != null) {
        if (isCredentialInvalid(r['error'])) {
          onCredentialInvalid();
          throw Exception('Could not validate credentials');
        }
        throw Exception('${r['error']}');
      }
      if (!context.mounted || seq != _weatherSeq) return;
      applyWeatherPayload(r, fallback: false);
    } catch (e) {
      if (!context.mounted || seq != _weatherSeq) return;
      if (e is StateError && e.message == 'location_service_disabled') {
        weatherLoading = false;
        notifyListeners();
        await pickManualCityWeather(context, seq: seq);
        return;
      }
      final canKeepLast = smartOutfitHadReliableWeatherSnapshot(
        fallback: prevFallback,
        full: prevFull,
        disp: prevDisp,
        city: prevCity,
      );
      if (canKeepLast) {
        weatherFallback = prevFallback;
        fullAddressLine = prevFull;
        displayAddress = prevDisp;
        cityShort = prevCity;
        weather = prevWeather;
        temp = prevTemp;
        weatherLoading = false;
        notifyListeners();
        _persistWeatherToPrefs();
        if (!context.mounted) return;
        showAppSnackBar(
          context,
          smartOutfitWeatherFailureHint(e),
          backgroundColor: palette.textBody,
        );
        return;
      }
      weatherFallback = true;
      fullAddressLine = '';
      displayAddress = '';
      cityShort = '默认';
      weather = '晴';
      temp = 22;
      weatherLoading = false;
      notifyListeners();
      _persistWeatherToPrefs();
      showAppSnackBar(
        context,
        smartOutfitWeatherFailureHint(e),
        backgroundColor: palette.textBody,
      );
    } finally {
      if (seq == _weatherSeq) {
        weatherRequestInFlight = false;
      }
    }
  }

  /// 手动省市区 + 可选街道，再按地名拉天气。
  Future<void> pickManualCityWeather(
    BuildContext context, {
    int? seq,
  }) async {
    final palette = context.read<ThemeProvider>().palette;
    final mySeq = seq ?? _weatherSeq;

    final r = await CityPickers.showCityPicker(
      context: context,
      showType: ShowType.pcav,
      theme: Theme.of(context).copyWith(
        colorScheme: Theme.of(context).colorScheme.copyWith(
              primary: palette.primary,
            ),
      ),
      height: 420,
      barrierDismissible: true,
    );
    if (!context.mounted || mySeq != _weatherSeq) return;
    if (r == null) return;

    final streetCtrl = TextEditingController();
    String? extraStreet;
    try {
      extraStreet = await showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
          title: const Text('道路 / 街道（可选）'),
          content: TextField(
            controller: streetCtrl,
            decoration: const InputDecoration(
              hintText: '例如：某某路、某某街道；可留空',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, ''),
              child: const Text('跳过'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, streetCtrl.text.trim()),
              child: const Text('确定'),
            ),
          ],
        ),
      );
    } finally {
      streetCtrl.dispose();
    }
    if (!context.mounted || mySeq != _weatherSeq) return;

    final parts = <String>[
      if (r.provinceName != null && r.provinceName!.trim().isNotEmpty)
        r.provinceName!.trim(),
      if (r.cityName != null && r.cityName!.trim().isNotEmpty)
        r.cityName!.trim(),
      if (r.areaName != null && r.areaName!.trim().isNotEmpty)
        r.areaName!.trim(),
      if (r.villageName != null && r.villageName!.trim().isNotEmpty)
        r.villageName!.trim(),
    ];
    var q = parts.join('');
    final st = extraStreet ?? '';
    if (st.isNotEmpty) {
      q = '$q$st';
    }

    if (q.isEmpty) {
      showAppSnackBar(context, '未选择有效地址');
      return;
    }

    await waitForAuthReady(context);
    if (!context.mounted || mySeq != _weatherSeq) return;
    if (!context.read<AuthProvider>().isAuthenticated) {
      showAppSnackBar(context, '请先登录后再获取天气');
      return;
    }
    final api = context.read<AuthProvider>().apiClient;

    weatherLoading = true;
    notifyListeners();
    try {
      final res = await api.getSmartOutfitWeatherByCity(q);
      if (res['error'] != null) {
        final res2 = await api
            .getSmartOutfitWeatherByCity(parts.length >= 2 ? parts[1] : q);
        if (res2['error'] != null) {
          if (context.mounted) {
            showAppSnackBar(context, '未找到该地区天气，请重试或换个地名');
            weatherLoading = false;
            notifyListeners();
          }
          return;
        }
        if (!context.mounted || mySeq != _weatherSeq) return;
        applyWeatherPayload(res2, fallback: false);
        return;
      }
      if (!context.mounted || mySeq != _weatherSeq) return;
      applyWeatherPayload(res, fallback: false);
    } catch (e) {
      if (context.mounted) {
        showAppSnackBar(context, '天气获取失败：$e');
        weatherLoading = false;
        notifyListeners();
      }
    }
  }

  void replaceReferenceImages(List<XFile> next) {
    _images.clear();
    _images.addAll(next);
    imageUrl = null;
    referenceCategory = null;
    referenceColorName = null;
    referenceRecognition = const {};
    outfits = [];
    regenIndex = 0;
    notifyListeners();
  }

  /// 从衣橱直接设置参考图 URL，跳过上传步骤。
  void setWardrobeReference(String url, {String? category}) {
    _images.clear();
    imageUrl = url;
    referenceCategory = category;
    referenceColorName = null;
    referenceRecognition = {
      if (category != null && category.isNotEmpty) 'category': category,
      'category_source': 'wardrobe',
    };
    outfits = [];
    regenIndex = 0;
    notifyListeners();
  }

  void setReferenceCategory(String value) {
    referenceCategory = value.trim().isEmpty ? null : value.trim();
    notifyListeners();
  }

  void setReferenceColorName(String value) {
    referenceColorName = value.trim().isEmpty ? null : value.trim();
    notifyListeners();
  }

  void _applyReferenceUploadResult(Map<String, dynamic> r) {
    final category = r['category']?.toString().trim();
    final mainColor = r['main_color'];
    final colorName =
        mainColor is Map ? mainColor['name']?.toString().trim() : null;
    final lowConfidence = r['reference_low_confidence'] == true;
    referenceRecognition = Map<String, dynamic>.from(r);
    if (!lowConfidence && category != null && category.isNotEmpty) {
      referenceCategory = category;
    } else if (lowConfidence) {
      referenceCategory = null;
    }
    if (!lowConfidence && colorName != null && colorName.isNotEmpty) {
      referenceColorName = colorName;
    } else if (lowConfidence) {
      referenceColorName = null;
    }
  }

  Future<void> ensureUploaded(ApiClient api) async {
    if (imageUrl != null && imageUrl!.isNotEmpty) return;
    if (_images.isEmpty) {
      throw StateError('no_reference_image');
    }
    final r = await api.uploadSmartOutfitReference(_images.first);
    if (r['error'] != null) {
      throw Exception(r['error']);
    }
    final url = r['image_url']?.toString();
    if (url == null || url.isEmpty) {
      throw Exception('无 image_url');
    }
    imageUrl = url;
    _applyReferenceUploadResult(r);
    _images.clear();
    notifyListeners();
  }

  Future<void> prepareReferenceRecognition(ApiClient api) async {
    if (_images.isEmpty || (imageUrl != null && imageUrl!.isNotEmpty)) return;
    referenceUploading = true;
    notifyListeners();
    try {
      await ensureUploaded(api);
    } finally {
      referenceUploading = false;
      notifyListeners();
    }
  }

  Future<SmartOutfitGenerateResult> generateSmartOutfit({
    required ApiClient api,
    required bool isAuthenticated,
    required String mood,
    required double? genderExpression,
    required bool regen,
  }) async {
    if (_images.isEmpty && (imageUrl == null || imageUrl!.isEmpty)) {
      return SmartOutfitGenerateResult.needImage();
    }
    if (!isAuthenticated) {
      return SmartOutfitGenerateResult.notAuthenticated();
    }

    generating = true;
    if (regen) {
      regenIndex++;
    } else {
      regenIndex = 0;
      outfits = [];
    }
    notifyListeners();

    try {
      await ensureUploaded(api);
      if (needsReferenceCategoryConfirmation) {
        return SmartOutfitGenerateResult.needReferenceCategory();
      }
      final r = await api.generateSmartOutfit(
        imageUrl: imageUrl!,
        location: locationForApi,
        city: cityShort,
        address: addressParts,
        weather: weather,
        temperature: temp,
        mood: mood,
        count: 3,
        regenerationIndex: regenIndex,
        genderExpression: genderExpression,
        referenceCategory: referenceCategory,
        referenceColorName: referenceColorName,
      );
      if (r['error'] != null) {
        final err = r['error'];
        if (isCredentialInvalid(err)) {
          return SmartOutfitGenerateResult.credentialInvalid();
        }
        return SmartOutfitGenerateResult.apiError(
          err,
          connectionRetrySuggested: _suggestConnectionRetry(err),
        );
      }
      final list = r['outfits'];
      if (list is! List || list.isEmpty) {
        return SmartOutfitGenerateResult.emptyOutfits();
      }
      outfits = list.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      notifyListeners();
      return SmartOutfitGenerateResult.success(outfits);
    } catch (e) {
      if (isCredentialInvalid(e)) {
        return SmartOutfitGenerateResult.credentialInvalid();
      }
      return SmartOutfitGenerateResult.apiError(
        e,
        connectionRetrySuggested: _suggestConnectionRetry(e),
      );
    } finally {
      generating = false;
      notifyListeners();
    }
  }

  void setOneTapBusy(bool v) {
    if (oneTapBusy == v) return;
    oneTapBusy = v;
    notifyListeners();
  }
}
