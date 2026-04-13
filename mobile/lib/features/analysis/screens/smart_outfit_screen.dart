import 'dart:convert';
import 'dart:math' as math;

import 'package:city_pickers/city_pickers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/utils/app_snackbar.dart'
    show showAppSnackBar, userFacingApiError;
import '../../../core/utils/media_url.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart'
    show extractOutfitGarmentIds;
import '../../../core/widgets/image_picker_section.dart';
import '../../../core/widgets/platform_image.dart';

/// 智能穿搭：参考图 + 自动天气 + 可选情绪 → 3 套衣橱搭配，可重新生成。
/// 定位：浏览器/系统高精度 GPS（非 IP）；地址由服务端逆地理解析；失败时四级行政区选择器降级。
class SmartOutfitScreen extends StatefulWidget {
  final bool autoPickAndGenerate;
  final int initialResultIndex;

  const SmartOutfitScreen({
    super.key,
    this.autoPickAndGenerate = false,
    this.initialResultIndex = 0,
  });

  @override
  State<SmartOutfitScreen> createState() => _SmartOutfitScreenState();
}

class _SmartOutfitScreenState extends State<SmartOutfitScreen> {
  final List<XFile> _images = [];
  String? _imageUrl;
  final _moodCtrl = TextEditingController();

  /// 短地名（接口 city 字段）
  String _cityShort = '';

  Map<String, String> _addressParts = const {};

  /// 服务端逆地理完整一行（省 市 区 街道），**禁止展示经纬度**
  String _fullAddressLine = '';
  String _displayAddress = '';
  String _weather = '晴';
  double _temp = 20;
  bool _weatherLoading = true;
  bool _weatherFallback = false;

  List<Map<String, dynamic>> _outfits = [];
  int _currentOutfitIndex = 0;
  bool _generating = false;
  bool _oneTapBusy = false;
  bool _didJumpToInitialIndex = false;
  int _regenIndex = 0;

  /// 1.0 避免 Web 窄屏下右侧露出下一张卡片被裁切；左右留白由卡片 Padding 承担。
  final _pageCtrl = PageController(viewportFraction: 1.0);

  /// 防止异步乱序与重复点击导致状态错乱
  int _weatherSeq = 0;
  bool _weatherRequestInFlight = false;

  /// 上报「喜欢/采纳」到 `POST /feedback/events`（与场景穿搭页一致）
  bool _outfitFeedbackBusy = false;

  /// 等待 [AuthProvider] 从 SharedPreferences 恢复 token。
  /// 若抢先调用天气/生成接口，请求无 Authorization → 401 → 误报「无法获取天气」或生成失败。
  Future<void> _waitForAuthReady() async {
    if (!mounted) return;
    var auth = context.read<AuthProvider>();
    if (auth.isInitialized) return;
    const step = Duration(milliseconds: 16);
    for (var i = 0; i < 200; i++) {
      await Future.delayed(step);
      if (!mounted) return;
      auth = context.read<AuthProvider>();
      if (auth.isInitialized) return;
    }
  }

  bool _isCredentialInvalidError(Object? error) {
    final s = (error?.toString() ?? '').toLowerCase();
    return s.contains('could not validate credentials') ||
        s.contains('not authenticated') ||
        s.contains('401');
  }

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
      final city = _cityShort.trim();
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
    Future.microtask(_restoreCachedThenFetch);
    if (widget.autoPickAndGenerate) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _oneTapGenerate();
      });
    }
  }

  Future<void> _restoreCachedThenFetch() async {
    await _restoreWeatherCache();
    if (!mounted) return;
    await _loadWeatherFromGps();
  }

  @override
  void dispose() {
    _moodCtrl.dispose();
    _pageCtrl.dispose();
    super.dispose();
  }

  /// Web：高精度；超时 25s（与天气接口一致，避免用户点「允许」稍慢即失败）。
  ///
  /// 注意：浏览器可能返回“粗略位置”(approximate) 或复用缓存坐标。
  /// 为提升精度，默认尽量拿“新鲜坐标”（maximumAge 很小），必要时再重试一次。
  LocationSettings _gpsLocationSettings({bool preferFresh = true}) {
    if (kIsWeb) {
      return WebSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 0,
        timeLimit: const Duration(seconds: 25),
        maximumAge: preferFresh
            ? const Duration(seconds: 2)
            : const Duration(seconds: 45),
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 0,
      timeLimit: Duration(seconds: 20),
    );
  }

  bool _isPoorAccuracy(Position p) {
    // accuracy 单位：米；> 500 通常是粗略定位（Wi‑Fi/IP 级）或权限未开“精确位置”
    final a = p.accuracy;
    return a.isNaN || a <= 0 || a > 500;
  }

  Future<Position> _getCurrentPositionWithRetry() async {
    Object? last;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        // 第一次尽量拿新鲜坐标；若精度仍很差，允许再等一次（浏览器/系统可能需要更多时间收敛）
        final p = await Geolocator.getCurrentPosition(
          locationSettings: _gpsLocationSettings(preferFresh: true),
        );
        if (attempt == 0 && _isPoorAccuracy(p)) {
          await Future.delayed(const Duration(milliseconds: 900));
          final p2 = await Geolocator.getCurrentPosition(
            locationSettings: _gpsLocationSettings(preferFresh: true),
          );
          return _isPoorAccuracy(p2) ? p : p2;
        }
        return p;
      } catch (e) {
        last = e;
        if (attempt < 1) {
          await Future.delayed(const Duration(milliseconds: 700));
        }
      }
    }
    throw (last ?? StateError('position'));
  }

  /// 上次展示是否可作为失败回退（非默认占位、非失败态）
  bool _hadReliableWeatherSnapshot({
    required bool fallback,
    required String full,
    required String disp,
    required String city,
  }) {
    if (fallback) return false;
    if (city.trim() == '默认') return false;
    return full.trim().isNotEmpty ||
        disp.trim().isNotEmpty ||
        city.trim().isNotEmpty;
  }

  String _weatherFailureHint(Object e) {
    final s = e.toString();
    if (s.contains('401')) {
      return '登录已失效或无效，请重新登录后再试定位与天气';
    }
    if (s.contains('403')) {
      return '没有权限访问天气接口，请检查账号';
    }
    if (s.contains('503') || s.toLowerCase().contains('unavailable')) {
      return '天气服务暂时不可用，请稍后重试';
    }
    return '无法更新位置或天气，仍显示上次定位；或请使用「手动选择地址」';
  }

  Future<void> _persistWeatherCache() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString('smart_outfit_full_address', _fullAddressLine);
      await p.setString('smart_outfit_city_short', _cityShort);
      await p.setString('smart_outfit_weather', _weather);
      await p.setDouble('smart_outfit_temp', _temp);
      await p.setBool('smart_outfit_fallback', _weatherFallback);
    } catch (_) {}
  }

  Future<void> _restoreWeatherCache() async {
    try {
      final p = await SharedPreferences.getInstance();
      final fa = p.getString('smart_outfit_full_address');
      if (fa == null || fa.isEmpty) return;
      if (!mounted) return;
      setState(() {
        _fullAddressLine = fa;
        _displayAddress = fa;
        _cityShort = p.getString('smart_outfit_city_short') ?? '';
        _weather = p.getString('smart_outfit_weather') ?? '晴';
        _temp = p.getDouble('smart_outfit_temp') ?? 20;
        _weatherFallback = p.getBool('smart_outfit_fallback') ?? false;
        _weatherLoading = false;
      });
    } catch (_) {}
  }

  void _applyWeatherPayload(Map<String, dynamic> r, {required bool fallback}) {
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
    setState(() {
      _addressParts = {
        if (p.isNotEmpty) 'province': p,
        if (c.isNotEmpty) 'city': c,
        if (d.isNotEmpty) 'district': d,
        if (s.isNotEmpty) 'street': s,
      };
      _fullAddressLine = full.isNotEmpty ? full : disp;
      _displayAddress = disp;
      _cityShort = city != null && city.isNotEmpty ? city : '';
      _weather = r['weather']?.toString() ?? '晴';
      _temp = (r['temperature'] as num?)?.toDouble() ?? 20;
      _weatherFallback = fallback;
      _weatherLoading = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _persistWeatherCache());
  }

  /// 人类可读地址（不含经纬度）
  String _humanAddressLine() {
    if (_displayAddress.trim().isNotEmpty) return _displayAddress.trim();
    if (_fullAddressLine.trim().isNotEmpty) return _fullAddressLine.trim();
    if (_cityShort.trim().isNotEmpty) return _cityShort.trim();
    return _weatherLoading ? '正在解析地址…' : '定位解析失败，请手动选择';
  }

  /// 生成接口 `location` 参数：完整地址，不用经纬度
  String get _locationForApi {
    return _fullAddressLine.trim().isNotEmpty
        ? _fullAddressLine.trim()
        : _displayAddress.trim().isNotEmpty
            ? _displayAddress.trim()
            : _cityShort.trim();
  }

  /// 清空旧定位后重新请求 GPS → 天气
  Future<void> _reloadGpsWeather() async {
    if (_weatherRequestInFlight) return;
    setState(() {
      _fullAddressLine = '';
      _displayAddress = '';
      _cityShort = '';
    });
    await _loadWeatherFromGps();
  }

  Future<void> _loadWeatherFromGps() async {
    if (_weatherRequestInFlight) return;
    await _waitForAuthReady();
    if (!mounted) return;
    final auth0 = context.read<AuthProvider>();
    if (!auth0.isAuthenticated) {
      if (mounted) setState(() => _weatherLoading = false);
      return;
    }

    // 确保 token 已写入 ApiClient（与 isInitialized 竞态时偶发无 Authorization → 401）
    for (var i = 0; i < 80; i++) {
      if (auth0.token != null && auth0.token!.isNotEmpty) break;
      await Future.delayed(const Duration(milliseconds: 25));
      if (!mounted) return;
    }

    final prevFallback = _weatherFallback;
    final prevFull = _fullAddressLine;
    final prevDisp = _displayAddress;
    final prevCity = _cityShort;
    final prevWeather = _weather;
    final prevTemp = _temp;

    _weatherRequestInFlight = true;
    final seq = ++_weatherSeq;
    final api = context.read<AuthProvider>().apiClient;
    final palette = context.read<ThemeProvider>().palette;

    try {
      if (!mounted) return;
      setState(() {
        _weatherLoading = true;
        _weatherFallback = false;
      });

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
        if (!mounted || seq != _weatherSeq) return;
        setState(() => _weatherLoading = false);
        await _showManualAddressPicker();
        return;
      }

      final pos = await _getCurrentPositionWithRetry();
      if (mounted && _isPoorAccuracy(pos)) {
        showAppSnackBar(
          context,
          '当前位置精度较低（≈${pos.accuracy.toStringAsFixed(0)}m）。'
          '请在浏览器地址栏左侧「位置」权限中选择“精确位置”，或改用「手动选择地址」。',
          backgroundColor: palette.textBody,
        );
      }
      final r = await api.getSmartOutfitWeather(pos.latitude, pos.longitude);
      if (r['error'] != null) {
        if (_isCredentialInvalidError(r['error'])) {
          _handleCredentialInvalid();
          throw Exception('Could not validate credentials');
        }
        throw Exception('${r['error']}');
      }
      if (!mounted || seq != _weatherSeq) return;
      _applyWeatherPayload(r, fallback: false);
    } catch (e) {
      if (!mounted || seq != _weatherSeq) return;
      if (e is StateError && e.message == 'location_service_disabled') {
        setState(() => _weatherLoading = false);
        await _showManualAddressPicker();
        return;
      }
      final canKeepLast = _hadReliableWeatherSnapshot(
        fallback: prevFallback,
        full: prevFull,
        disp: prevDisp,
        city: prevCity,
      );
      if (canKeepLast) {
        setState(() {
          _weatherFallback = prevFallback;
          _fullAddressLine = prevFull;
          _displayAddress = prevDisp;
          _cityShort = prevCity;
          _weather = prevWeather;
          _temp = prevTemp;
          _weatherLoading = false;
        });
        _persistWeatherCache();
        if (!mounted) return;
        showAppSnackBar(
          context,
          _weatherFailureHint(e),
          backgroundColor: palette.textBody,
        );
        return;
      }
      setState(() {
        _weatherFallback = true;
        _fullAddressLine = '';
        _displayAddress = '';
        _cityShort = '默认';
        _weather = '晴';
        _temp = 22;
        _weatherLoading = false;
      });
      _persistWeatherCache();
      showAppSnackBar(
        context,
        _weatherFailureHint(e),
        backgroundColor: palette.textBody,
      );
    } finally {
      if (seq == _weatherSeq) {
        _weatherRequestInFlight = false;
      }
    }
  }

  /// 省 / 市 / 区 / 街道(镇) 四级；可选补充道路名；完成后按地名拉取天气
  Future<void> _showManualAddressPicker() async {
    final palette = context.read<ThemeProvider>().palette;
    final seq = _weatherSeq;

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
    if (!mounted || seq != _weatherSeq) return;
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
    if (!mounted || seq != _weatherSeq) return;

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

    await _waitForAuthReady();
    if (!mounted || seq != _weatherSeq) return;
    if (!context.read<AuthProvider>().isAuthenticated) {
      showAppSnackBar(context, '请先登录后再获取天气');
      return;
    }
    final api = context.read<AuthProvider>().apiClient;

    setState(() => _weatherLoading = true);
    try {
      final res = await api.getSmartOutfitWeatherByCity(q);
      if (res['error'] != null) {
        final res2 = await api
            .getSmartOutfitWeatherByCity(parts.length >= 2 ? parts[1] : q);
        if (res2['error'] != null) {
          if (mounted) {
            showAppSnackBar(context, '未找到该地区天气，请重试或换个地名');
            setState(() => _weatherLoading = false);
          }
          return;
        }
        if (!mounted || seq != _weatherSeq) return;
        _applyWeatherPayload(res2, fallback: false);
        return;
      }
      if (!mounted || seq != _weatherSeq) return;
      _applyWeatherPayload(res, fallback: false);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '天气获取失败：$e');
        setState(() => _weatherLoading = false);
      }
    }
  }

  Future<void> _ensureUploaded() async {
    if (_imageUrl != null && _imageUrl!.isNotEmpty) return;
    if (_images.isEmpty) return;
    final api = context.read<AuthProvider>().apiClient;
    final r = await api.uploadSmartOutfitReference(_images.first);
    if (r['error'] != null) {
      throw Exception(r['error']);
    }
    final url = r['image_url']?.toString();
    if (url == null || url.isEmpty) {
      throw Exception('无 image_url');
    }
    _imageUrl = url;
  }

  Future<void> _cacheTodayRecommendationAt(int index) async {
    try {
      if (_outfits.isEmpty) return;
      final safeIndex = index.clamp(0, _outfits.length - 1);
      final outfit = _outfits[safeIndex];
      final prefs = await SharedPreferences.getInstance();
      final ai = outfit['ai_recommendation'];
      final payload = {
        'city': _cityShort,
        'weather': _weather,
        'temperature': _temp,
        'recommendation_index': safeIndex,
        'updated_at': DateTime.now().toIso8601String(),
        'description': outfit['description']?.toString() ?? '',
        'preview_image_url': outfit['preview_image_url']?.toString() ?? '',
        'ai_recommendation': ai is Map ? Map<String, dynamic>.from(ai) : {},
      };
      await prefs.setString(
        'home_today_recommendation',
        jsonEncode(payload),
      );
      // 保持 json 版本，供首页稳定读取
      await prefs.setString(
        'home_today_recommendation_json',
        jsonEncode(payload),
      );
    } catch (_) {}
  }

  Future<void> _oneTapGenerate() async {
    if (_oneTapBusy || _generating) return;
    setState(() => _oneTapBusy = true);
    try {
      if (_images.isEmpty) {
        final picked = await _pickSingleImageWithSource();
        if (picked == null) {
          if (mounted) showAppSnackBar(context, '已取消选择图片');
          return;
        }
        if (!mounted) return;
        setState(() {
          _images
            ..clear()
            ..add(picked);
          _imageUrl = null;
          _outfits = [];
          _regenIndex = 0;
        });
      }
      if (_weatherLoading) {
        await _loadWeatherFromGps();
      }
      if (!mounted) return;
      await _generate(regen: false);
    } finally {
      if (mounted) setState(() => _oneTapBusy = false);
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

  void _maybeJumpToInitialIndex() {
    if (_didJumpToInitialIndex) return;
    final index = widget.initialResultIndex;
    if (index <= 0 || _outfits.isEmpty || index >= _outfits.length) {
      _didJumpToInitialIndex = true;
      _currentOutfitIndex = 0;
      return;
    }
    _didJumpToInitialIndex = true;
    _currentOutfitIndex = index;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_pageCtrl.hasClients) return;
      _pageCtrl.jumpToPage(index);
    });
  }

  Future<void> _generate({bool regen = false}) async {
    if (_images.isEmpty) {
      showAppSnackBar(context, '请先上传一张参考衣物图片');
      return;
    }
    await _waitForAuthReady();
    if (!mounted) return;
    final auth = context.read<AuthProvider>();
    if (!auth.isAuthenticated) {
      showAppSnackBar(context, '请先登录后再生成穿搭');
      return;
    }
    final ge = context.read<ThemeProvider>().genderExpression;

    setState(() {
      _generating = true;
      if (regen) {
        _regenIndex++;
      } else {
        _regenIndex = 0;
        _outfits = [];
      }
    });

    try {
      await _ensureUploaded();
      final r = await auth.apiClient.generateSmartOutfit(
        imageUrl: _imageUrl!,
        location: _locationForApi,
        city: _cityShort,
        address: _addressParts,
        weather: _weather,
        temperature: _temp,
        mood: _moodCtrl.text.trim(),
        count: 3,
        regenerationIndex: _regenIndex,
        genderExpression: ge,
      );
      if (r['error'] != null) {
        if (_isCredentialInvalidError(r['error'])) {
          if (mounted) {
            _handleCredentialInvalid();
          }
          setState(() => _generating = false);
          return;
        }
        if (mounted) {
          final msg = userFacingApiError(r['error']);
          final isConn = msg.contains('无法连接') || msg.contains('网络');
          showAppSnackBar(
            context,
            '生成失败：$msg',
            action: isConn
                ? SnackBarAction(
                    label: '重试',
                    textColor: Colors.white,
                    onPressed: () => _generate(regen: regen),
                  )
                : null,
          );
        }
        setState(() => _generating = false);
        return;
      }
      final list = r['outfits'];
      if (list is! List || list.isEmpty) {
        if (mounted) {
          showAppSnackBar(context, '暂无搭配结果，请重试或向衣橱添加单品');
        }
        setState(() {
          _generating = false;
          _outfits = [];
        });
        return;
      }
      if (!mounted) return;
      setState(() {
        _outfits =
            list.map((e) => Map<String, dynamic>.from(e as Map)).toList();
        _currentOutfitIndex = 0;
        _generating = false;
      });
      if (_outfits.isNotEmpty) {
        _maybeJumpToInitialIndex();
        await _cacheTodayRecommendationAt(_currentOutfitIndex);
      }
    } catch (e) {
      if (_isCredentialInvalidError(e)) {
        if (mounted) {
          _handleCredentialInvalid();
        }
        setState(() => _generating = false);
        return;
      }
      if (mounted) {
        final msg = userFacingApiError(e);
        final isConn = msg.contains('无法连接') || msg.contains('网络');
        showAppSnackBar(
          context,
          '生成失败：$msg',
          action: isConn
              ? SnackBarAction(
                  label: '重试',
                  textColor: Colors.white,
                  onPressed: () => _generate(regen: regen),
                )
              : null,
        );
      }
      setState(() => _generating = false);
    }
  }

  IconData _weatherIcon() {
    final w = _weather;
    if (w.contains('雨') || w.contains('雷')) return Icons.umbrella;
    if (w.contains('雪')) return Icons.ac_unit;
    if (w.contains('云') || w.contains('阴')) {
      return Icons.cloud_outlined;
    }
    return Icons.wb_sunny_outlined;
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    final apiBase = context.read<AuthProvider>().apiClient.baseUrl;

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
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              _SmartHintChip(
                                icon: Icons.add_photo_alternate_outlined,
                                text: '先上传清晰单品图',
                                color: Colors.blue,
                              ),
                              _SmartHintChip(
                                icon: Icons.my_location_outlined,
                                text: '定位越准越贴合天气',
                                color: Colors.green,
                              ),
                              _SmartHintChip(
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
                      images: _images,
                      onImagesChanged: (list) {
                        setState(() {
                          _images.clear();
                          _images.addAll(list);
                          _imageUrl = null;
                          _outfits = [];
                          _regenIndex = 0;
                        });
                      },
                      maxImages: 1,
                      hintText: '上传 1 张主参考衣物图',
                      allowMultiple: false,
                    ),
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
                        child: _weatherLoading
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
                                        _weatherIcon(),
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
                                              _weatherFallback
                                                  ? '未精准定位（默认参数）'
                                                  : '已精准定位',
                                              style: TextStyle(
                                                fontWeight: FontWeight.w700,
                                                fontSize: 14,
                                                color: palette.textTitle,
                                              ),
                                            ),
                                            const SizedBox(height: 8),
                                            _StructuredAddressView(
                                              palette: palette,
                                              addressParts: _addressParts,
                                              fallbackText: _weatherLoading
                                                  ? '正在解析地址…'
                                                  : _weatherFallback
                                                      ? '未获取到详细地址'
                                                      : '地址已就绪',
                                            ),
                                            const SizedBox(height: 10),
                                            Text(
                                              '当前天气：$_weather',
                                              style: TextStyle(
                                                fontSize: 14,
                                                height: 1.35,
                                                color: palette.textBody,
                                              ),
                                            ),
                                            const SizedBox(height: 4),
                                            Text(
                                              '当前温度：${_temp.toStringAsFixed(0)}℃',
                                              style: TextStyle(
                                                fontSize: 14,
                                                height: 1.35,
                                                color: palette.textBody,
                                              ),
                                            ),
                                            if (_weatherFallback)
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
                                        onPressed: _weatherRequestInFlight
                                            ? null
                                            : _reloadGpsWeather,
                                        icon: Icon(Icons.my_location,
                                            size: 18, color: palette.primary),
                                        label: const Text('重新获取定位'),
                                      ),
                                      TextButton.icon(
                                        style: TextButton.styleFrom(
                                          foregroundColor: palette.primary,
                                        ),
                                        onPressed: _weatherLoading
                                            ? null
                                            : _showManualAddressPicker,
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
                    _SmartSummaryCard(
                      palette: palette,
                      hasImage: _images.isNotEmpty,
                      weatherLoading: _weatherLoading,
                      weatherFallback: _weatherFallback,
                      addressParts: _addressParts,
                      moodText: _moodCtrl.text.trim(),
                      hasResult: _outfits.isNotEmpty,
                    ),
                    const SizedBox(height: 20),
                    FilledButton.icon(
                      onPressed:
                          (_oneTapBusy || _generating) ? null : _oneTapGenerate,
                      icon: (_oneTapBusy || _generating)
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
                        (_oneTapBusy || _generating) ? '正在一键生成…' : '一键生成穿搭',
                      ),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(22),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (_outfits.isEmpty)
                      FilledButton.icon(
                        onPressed:
                            _generating ? null : () => _generate(regen: false),
                        icon: _generating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.auto_awesome),
                        label: Text(_generating ? '正在为你生成专属穿搭…' : '生成穿搭'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(22),
                          ),
                        ),
                      )
                    else
                      FilledButton.icon(
                        onPressed:
                            _generating ? null : () => _generate(regen: true),
                        icon: _generating
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.refresh),
                        label: Text(_generating ? '正在为你生成专属穿搭…' : '重新生成'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(22),
                          ),
                        ),
                      ),
                    if (_outfits.isNotEmpty) ...[
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
                        children: List.generate(_outfits.length, (index) {
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
                        behavior: const _MouseDragScrollBehavior(),
                        child: SizedBox(
                          height: pageViewH,
                          child: PageView.builder(
                            controller: _pageCtrl,
                            itemCount: _outfits.length,
                            onPageChanged: (index) {
                              if (!mounted) return;
                              setState(() {
                                _currentOutfitIndex = index;
                              });
                              _cacheTodayRecommendationAt(index);
                            },
                            itemBuilder: (_, i) {
                              final o = _outfits[i];
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
                                                            ),
                                                          ),
                                                          Text(
                                                            m['category']
                                                                    ?.toString() ??
                                                                '',
                                                            style: TextStyle(
                                                              fontSize: 12,
                                                              color: palette
                                                                  .textBody,
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

/// Web / 桌面端：默认 [ScrollBehavior] 不把鼠标拖拽算作 PageView 滑动，需包含 [PointerDeviceKind.mouse]。
class _MouseDragScrollBehavior extends MaterialScrollBehavior {
  const _MouseDragScrollBehavior();

  @override
  Set<PointerDeviceKind> get dragDevices => {
        PointerDeviceKind.touch,
        PointerDeviceKind.mouse,
        PointerDeviceKind.trackpad,
        PointerDeviceKind.stylus,
      };
}

class _SmartHintChip extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;

  const _SmartHintChip({
    required this.icon,
    required this.text,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: color.withValues(alpha: 0.95),
            ),
          ),
        ],
      ),
    );
  }
}

class _StructuredAddressView extends StatelessWidget {
  final dynamic palette;
  final Map<String, String> addressParts;
  final String fallbackText;

  const _StructuredAddressView({
    required this.palette,
    required this.addressParts,
    required this.fallbackText,
  });

  @override
  Widget build(BuildContext context) {
    final chips = <Widget>[];
    void addChip(String label, String key, Color color) {
      final value = addressParts[key]?.trim() ?? '';
      if (value.isEmpty) return;
      chips.add(_AddressChip(label: label, value: value, color: color));
    }

    addChip('省', 'province', Colors.blue);
    addChip('市', 'city', Colors.green);
    addChip('区', 'district', Colors.orange);
    addChip('街道', 'street', Colors.purple);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: palette.divider.withValues(alpha: 0.9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '地址信息',
            style: TextStyle(
              color: palette.textTitle,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          if (chips.isEmpty)
            Text(
              fallbackText,
              style: TextStyle(
                color: palette.textBody,
                fontSize: 11,
              ),
            )
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: chips,
            ),
        ],
      ),
    );
  }
}

class _AddressChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _AddressChip({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color.withValues(alpha: 0.95),
        ),
      ),
    );
  }
}

class _SmartSummaryCard extends StatelessWidget {
  final dynamic palette;
  final bool hasImage;
  final bool weatherLoading;
  final bool weatherFallback;
  final Map<String, String> addressParts;
  final String moodText;
  final bool hasResult;

  const _SmartSummaryCard({
    required this.palette,
    required this.hasImage,
    required this.weatherLoading,
    required this.weatherFallback,
    required this.addressParts,
    required this.moodText,
    required this.hasResult,
  });

  @override
  Widget build(BuildContext context) {
    final weatherStatus = weatherLoading
        ? '天气加载中'
        : weatherFallback
            ? '默认天气参数'
            : '定位天气就绪';
    final moodStatus = moodText.isEmpty ? '未填写（可选）' : '已填写';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: palette.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.primary.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '生成前状态',
            style: TextStyle(
              color: palette.textTitle,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '参考图：${hasImage ? '已上传' : '未上传'}  |  天气：$weatherStatus  |  心情：$moodStatus',
            style: TextStyle(
              color: palette.textBody,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 8),
          _StructuredAddressView(
            palette: palette,
            addressParts: addressParts,
            fallbackText: weatherLoading
                ? '正在解析地址…'
                : weatherFallback
                    ? '未获取到详细地址'
                    : '地址已就绪',
          ),
          if (hasResult) ...[
            const SizedBox(height: 6),
            Text(
              '已生成结果，可点击“重新生成”获取另一组方案。',
              style: TextStyle(
                color: palette.textBody,
                fontSize: 11,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
