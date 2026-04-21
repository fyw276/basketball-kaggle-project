import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';

import 'api_base_resolver.dart';
import 'api_port_config.dart';

/// 智能穿搭：情绪字段去控制字符、折叠空白、限长，保证 JSON 与后端解析稳定。
String _normalizeSmartOutfitMood(String mood) {
  var s = mood.trim();
  if (s.isEmpty) {
    return '';
  }
  final buf = StringBuffer();
  for (final r in s.runes) {
    if (r == 0x9 || r == 0xA || r == 0xD) {
      buf.write(' ');
    } else if (r < 0x20) {
      continue;
    } else {
      buf.writeCharCode(r);
    }
  }
  s = buf.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
  if (s.length > 500) {
    s = s.substring(0, 500);
  }
  return s;
}

/// 解包统一 API envelope：`{success, data, error}`。
///
/// 成功返回 `data`，失败优先提取 `error.message`，否则回退到 `message` 或原对象。
dynamic unwrapApiResponseEnvelope(dynamic decoded) {
  if (decoded is Map &&
      decoded.containsKey('success') &&
      decoded.containsKey('data') &&
      decoded.containsKey('error')) {
    if (decoded['success'] == true) {
      return decoded['data'];
    }
    final error = decoded['error'];
    if (error is Map && error['message'] != null) {
      return {'error': error['message'].toString()};
    }
    return {'error': decoded['message']?.toString() ?? 'Request failed'};
  }
  return decoded;
}

/// 提取 FastAPI 常见错误响应里的可读文本。
String? parseFastApiErrorBody(String body) {
  if (body.isEmpty) return null;
  try {
    final decoded = json.decode(body);
    if (decoded is Map) {
      if (decoded['detail'] != null) {
        return decoded['detail'].toString();
      }
      final error = decoded['error'];
      if (error is Map && error['message'] != null) {
        return error['message'].toString();
      }
      if (decoded['message'] != null) {
        return decoded['message'].toString();
      }
    }
  } catch (_) {}
  return null;
}

class ApiClient {
  final String baseUrl;
  String? _token;

  /// Set when the last [getList] call failed (non-200 or exception). Cleared on each new [getList].
  /// Use for diagnostics / snackbars; list endpoints still return `[]` for backward compatibility.
  String? lastGetListError;

  ApiClient({String? baseUrl})
      : baseUrl =
            (baseUrl ?? kDefaultApiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  void setToken(String token) {
    _token = token;
  }

  void clearToken() {
    _token = null;
  }

  Map<String, String> get _jsonHeaders => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Map<String, String> get _authHeaders {
    final h = <String, String>{};
    if (_token != null) h['Authorization'] = 'Bearer $_token';
    return h;
  }

  String _resolveV2BaseUrl() {
    final trimmed = baseUrl.replaceAll(RegExp(r'/+$'), '');
    if (trimmed.endsWith('/api/v2')) return trimmed;
    final upgraded = trimmed.replaceFirst(RegExp(r'/api/v1$'), '/api/v2');
    if (upgraded != trimmed) return upgraded;
    if (trimmed.endsWith('/api')) return '$trimmed/v2';
    return '$trimmed/api/v2';
  }

  // ─── 工具：Web / 移动端统一用字节上传（避免 MultipartFile.fromPath 在 Web 不可用）──

  static Future<http.MultipartFile?> _multipartImage(
    String fieldName,
    dynamic imageFile,
  ) async {
    if (imageFile == null) return null;
    final XFile xf;
    if (imageFile is XFile) {
      xf = imageFile;
    } else if (imageFile is String) {
      xf = XFile(imageFile);
    } else {
      return null;
    }
    final bytes = await xf.readAsBytes();
    final name = xf.name;
    return http.MultipartFile.fromBytes(
      fieldName,
      bytes,
      filename: name.isNotEmpty ? name : 'upload.jpg',
      contentType: MediaType('image', 'jpeg'),
    );
  }

  // ─── JSON 请求 ──────────────────────────────────────────────────

  Future<Map<String, dynamic>> get(String path) async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
      );
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<dynamic> getList(String path) async {
    lastGetListError = null;
    try {
      final response = await http.get(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
      );
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is List) return unwrapped;
        if (unwrapped is Map && unwrapped['data'] is List)
          return unwrapped['data'];
        return unwrapped;
      }
      lastGetListError = parseFastApiErrorBody(response.body) ??
          'Request failed with status: ${response.statusCode}';
      return [];
    } catch (e) {
      lastGetListError = e.toString();
      return [];
    }
  }

  Future<Map<String, dynamic>> post(
      String path, Map<String, dynamic> data) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await http.post(
        uri,
        headers: _jsonHeaders,
        body: json.encode(data),
      );
      if (response.statusCode == 200 || response.statusCode == 201) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 404) {
        return {
          'error': 'Request failed with status: 404 ($uri)。'
              '请确认已启动本仓库后端且端口一致（默认 8010，见 backend/.env 的 PORT）。'
              '浏览器打开 http://127.0.0.1:<端口>/ 应返回 Smart Outfit Assistant。',
        };
      }
      if (response.body.isNotEmpty) {
        try {
          final decoded = json.decode(response.body);
          final unwrapped = unwrapApiResponseEnvelope(decoded);
          if (unwrapped is Map && unwrapped['error'] != null) {
            return {'error': unwrapped['error'].toString()};
          }
          if (decoded is Map && decoded['detail'] != null) {
            final detail = decoded['detail'];
            if (detail is String) {
              return {'error': detail};
            }
          }
        } catch (_) {
          // Fall back to generic status error.
        }
      }
      return {
        'error': 'Request failed with status: ${response.statusCode} ($uri)',
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// AI 穿搭风格分：`POST /predict`（默认 `127.0.0.1:8010`，与当前后端主服务一致）。
  ///
  /// 成功时含 `score`、`recommendations`、`explanation`；失败时含 `error`。
  Future<Map<String, dynamic>> predictOutfitStyle(
    Map<String, dynamic> body,
  ) async {
    final base = resolvePredictApiBaseUrl().replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.parse('$base/predict');
    try {
      final response = await http.post(
        uri,
        headers: const {
          'Content-Type': 'application/json',
        },
        body: json.encode(body),
      );
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body) as dynamic;
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) {
          return Map<String, dynamic>.from(unwrapped);
        }
        return {'error': 'Unexpected /predict response shape'};
      }
      if (response.body.isNotEmpty) {
        try {
          final decoded = json.decode(response.body) as dynamic;
          final unwrapped = unwrapApiResponseEnvelope(decoded);
          if (unwrapped is Map && unwrapped['error'] != null) {
            return {'error': unwrapped['error'].toString()};
          }
          if (decoded is Map && decoded['detail'] != null) {
            final detail = decoded['detail'];
            if (detail is String) {
              return {'error': detail};
            }
          }
        } catch (_) {
          // fall through
        }
      }
      return {
        'error': 'Request failed with status: ${response.statusCode} ($uri)',
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> delete(String path) async {
    try {
      final response = await http.delete(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
      );
      if (response.statusCode == 200 || response.statusCode == 204) {
        if (response.body.isEmpty) {
          return <String, dynamic>{};
        }
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> patch(
      String path, Map<String, dynamic> data) async {
    try {
      final response = await http.patch(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
        body: json.encode(data),
      );
      if (response.statusCode == 200 || response.statusCode == 204) {
        if (response.body.isEmpty) {
          return <String, dynamic>{};
        }
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  // ─── Auth ──────────────────────────────────────────────────────

  Future<Map<String, dynamic>> register(
      String username, String email, String password,
      {String? phoneNumber}) async {
    final payload = <String, dynamic>{
      'username': username,
      'email': email,
      'password': password,
    };
    if (phoneNumber != null && phoneNumber.trim().isNotEmpty) {
      payload['phone_number'] = phoneNumber.trim();
    }
    return post('/auth/register', payload);
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final result = await post('/auth/login', {
      'username': username,
      'password': password,
    });
    if (result.containsKey('access_token')) {
      _token = result['access_token'];
    }
    return result;
  }

  Future<Map<String, dynamic>> logout() async {
    clearToken();
    return {'success': true};
  }

  // ─── Profile ──────────────────────────────────────────────────

  Future<Map<String, dynamic>> getProfile() async {
    return get('/profile/');
  }

  Future<Map<String, dynamic>> createProfile(Map<String, dynamic> data) async {
    return post('/profile/', data);
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> data) async {
    return post('/profile/', data);
  }

  // ─── 情绪穿搭（后端已有色彩心理学 + 衣橱匹配）────────────────────
  Future<Map<String, dynamic>> recommendByMood({
    required String mood,
    bool includeWardrobe = true,
  }) {
    return post('/mood/recommend', {
      'mood': mood,
      'include_wardrobe': includeWardrobe,
    });
  }

  Future<dynamic> getMoodQuickRecall() async {
    return getList('/mood/quick-recall');
  }

  // ─── 衣橱：衣物上传 ─────────────────────────────────────────────
  // 后端路由: POST /wardrobe/simple/garments
  // 后端字段: file=UploadFile, notes=Optional[str]

  Future<Map<String, dynamic>> addGarment({
    dynamic imageFile,
    String? category,
    String? color,
    String? style,
    String? season,
    String? genderLabel,
    double? neutralScore,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/wardrobe/simple/garments'),
      );
      request.headers.addAll(_authHeaders);

      if (imageFile != null) {
        final part = await _multipartImage('file', imageFile);
        if (part == null) {
          return {'error': 'Unsupported image type: ${imageFile.runtimeType}'};
        }
        request.files.add(part);
      }

      if (category != null) request.fields['category'] = category;
      if (color != null) request.fields['color'] = color;
      if (style != null) request.fields['style'] = style;
      if (season != null) request.fields['season'] = season;
      if (genderLabel != null) request.fields['gender_label'] = genderLabel;
      if (neutralScore != null) {
        request.fields['neutral_score'] = neutralScore.toString();
      }

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 30),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200 || response.statusCode == 201) {
        final decoded = json.decode(response.body) as dynamic;
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        if (unwrapped is List) return {'data': unwrapped};
        return {'data': unwrapped};
      }
      final err = parseFastApiErrorBody(response.body);
      if (err != null && err.trim().isNotEmpty) {
        return {'error': err};
      }
      return {'error': 'Upload failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> addGarmentFromXFile(
    dynamic imageFile, {
    String? category,
    String? color,
    String? style,
    String? season,
    String? genderLabel,
    double? neutralScore,
  }) =>
      addGarment(
        imageFile: imageFile,
        category: category,
        color: color,
        style: style,
        season: season,
        genderLabel: genderLabel,
        neutralScore: neutralScore,
      );

  // ─── 衣橱：获取衣物列表 ─────────────────────────────────────────
  // 后端返回: GarmentListResponse { total, page, page_size, items }

  Future<List<Map<String, dynamic>>> getGarments({
    String? category,
    String? color,
    String? style,
    int page = 1,
    int pageSize = 100,
  }) async {
    final params = <String>[
      'page=$page',
      'page_size=$pageSize',
    ];
    if (category != null) params.add('category=$category');
    if (color != null) params.add('color=$color');
    if (style != null) params.add('style=$style');
    final query = '?${params.join('&')}';

    final raw = await getList('/wardrobe/simple/garments$query');

    if (raw is Map) {
      final items = raw['items'];
      if (items is List) {
        return items.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      }
    }
    if (raw is List) {
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    return [];
  }

  Future<Map<String, dynamic>> deleteGarment(String garmentId) async {
    return delete('/wardrobe/simple/garments/$garmentId');
  }

  Future<Map<String, dynamic>> updateGarmentCategory(
      String garmentId, String category) async {
    return patch(
        '/wardrobe/simple/garments/$garmentId', {'category': category});
  }

  Future<Map<String, dynamic>> repairGarmentImageUrls() async {
    return post('/wardrobe/simple/garments/repair-image-urls', {});
  }

  /// Re-run color (and optionally category) from the stored image file.
  Future<Map<String, dynamic>> reanalyzeGarmentVisual(
    String garmentId, {
    bool recategorize = false,
  }) async {
    final q = recategorize ? '?recategorize=true' : '';
    return post('/wardrobe/simple/garments/$garmentId/reanalyze-visual$q', {});
  }

  // ─── 衣橱：整套拆分上传 ─────────────────────────────────────────
  // 后端路由: POST /wardrobe/split-outfit
  // 后端字段: file=UploadFile, save=bool, selected_indexes=逗号分隔字符串

  Future<dynamic> splitOutfitImage({
    dynamic imageFile,
    bool save = false,
    List<int>? selectedIndexes,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/wardrobe/split-outfit'),
      );
      request.headers.addAll(_authHeaders);

      if (imageFile != null) {
        final part = await _multipartImage('file', imageFile);
        if (part == null) return {'error': 'Unsupported image type'};
        request.files.add(part);
      }

      // 与 FastAPI Form 字段对应（勿用 Query + 仅写 form body，否则 save 无法绑定）
      request.fields['save'] = save.toString();
      if (selectedIndexes != null && selectedIndexes.isNotEmpty) {
        request.fields['selected_indexes'] = selectedIndexes.join(',');
      }

      // 拆分预览或 save=true 时后端会对每块裁剪跑 CLIP + 配色 + 入库，CPU 环境易超过 60s
      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 180),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        return unwrapApiResponseEnvelope(decoded);
      }
      return {'error': 'Split failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  // ─── 分析：相似度检测 ───────────────────────────────────────────
  // 后端路由: POST /analysis/similarity
  // 后端字段: file=UploadFile

  Future<Map<String, dynamic>> analyzeSimilarity({
    dynamic imageFile,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/analysis/similarity'),
      );
      request.headers.addAll(_authHeaders);

      if (imageFile != null) {
        final part = await _multipartImage('file', imageFile);
        if (part == null) return {'error': 'Unsupported image type'};
        request.files.add(part);
      }

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 120),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {'error': 'Analysis failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> analyzeSimilarityFromXFile(dynamic imageFile) =>
      analyzeSimilarity(imageFile: imageFile);

  // ─── 分析：穿搭推荐 ─────────────────────────────────────────────
  // 后端路由: POST /analysis/outfits
  // 后端字段: file=单图（兼容）或 files=多图（字段名 files，可重复）, num_outfits, gender_expression?, scene?

  Future<Map<String, dynamic>> recommendOutfits({
    dynamic imageFile,
    List<dynamic>? imageFiles,
    int numOutfits = 5,
    double? genderExpression,
    String? scene,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/analysis/outfits'),
      );
      request.headers.addAll(_authHeaders);

      final List<dynamic> parts = <dynamic>[];
      if (imageFiles != null && imageFiles.isNotEmpty) {
        parts.addAll(imageFiles);
      } else if (imageFile != null) {
        parts.add(imageFile);
      }
      if (parts.isEmpty) {
        return {'error': 'No image provided'};
      }
      // 多图：multipart 字段名 files（每张重复一次）；单图仍用 file 兼容旧调用
      if (parts.length == 1) {
        final part = await _multipartImage('file', parts.first);
        if (part == null) return {'error': 'Unsupported image type'};
        request.files.add(part);
      } else {
        for (final img in parts) {
          final part = await _multipartImage('files', img);
          if (part == null) return {'error': 'Unsupported image type'};
          request.files.add(part);
        }
      }

      request.fields['num_outfits'] = numOutfits.toString();
      if (genderExpression != null) {
        request.fields['gender_expression'] = genderExpression.toString();
      }
      if (scene != null) request.fields['scene'] = scene;

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 120),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {
        'error': 'Recommendation failed with status: ${response.statusCode}'
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> recommendOutfitsFromXFile(
    dynamic imageFile, {
    int numOutfits = 5,
    double? genderExpression,
    String? scene,
  }) =>
      recommendOutfits(
        imageFile: imageFile,
        numOutfits: numOutfits,
        genderExpression: genderExpression,
        scene: scene,
      );

  /// 多图穿搭推荐（同一请求内合并识别结果）。
  Future<Map<String, dynamic>> recommendOutfitsFromXFiles(
    List<dynamic> imageFiles, {
    int numOutfits = 5,
    double? genderExpression,
    String? scene,
  }) =>
      recommendOutfits(
        imageFiles: imageFiles,
        numOutfits: numOutfits,
        genderExpression: genderExpression,
        scene: scene,
      );

  /// 用户反馈：`POST /feedback/events`（喜欢/采纳等，用于后端重排与数据飞轮）
  Future<Map<String, dynamic>> submitFeedbackEvent({
    required String eventType,
    String source = 'analysis_outfit',
    String? garmentId,
    String? collectionId,
    String? scene,
    Map<String, dynamic>? payload,
  }) async {
    final body = <String, dynamic>{
      'event_type': eventType,
      'source': source,
      if (garmentId != null && garmentId.isNotEmpty) 'garment_id': garmentId,
      if (collectionId != null && collectionId.isNotEmpty)
        'collection_id': collectionId,
      if (scene != null && scene.isNotEmpty) 'scene': scene,
      if (payload != null) 'payload': payload,
    };
    return post('/feedback/events', body);
  }

  /// 套装收藏：`POST /outfits/collections`
  Future<Map<String, dynamic>> saveOutfitCollection({
    required String name,
    required String scene,
    String? description,
    required List<String> garmentIds,
  }) async {
    return post('/outfits/collections', {
      'name': name,
      'scene': scene,
      if (description != null && description.trim().isNotEmpty)
        'description': description.trim(),
      'garment_ids': garmentIds,
    });
  }

  // ─── 分析：适合度 ────────────────────────────────────────────────
  // 后端路由: POST /analysis/suitability
  // 后端字段: file=UploadFile, scene=Optional[str]

  Future<Map<String, dynamic>> analyzeSuitability({
    dynamic imageFile,
    String? scene,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/analysis/suitability'),
      );
      request.headers.addAll(_authHeaders);

      if (imageFile != null) {
        final part = await _multipartImage('file', imageFile);
        if (part == null) return {'error': 'Unsupported image type'};
        request.files.add(part);
      }

      if (scene != null) request.fields['scene'] = scene;

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 120),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      return {'error': 'Analysis failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> analyzeSuitabilityFromXFile(
    dynamic imageFile, {
    String? scene,
  }) =>
      analyzeSuitability(imageFile: imageFile, scene: scene);

  // ─── 分析：虚拟试衣 ───────────────────────────────────────────────
  // 后端路由: POST /tryon/garment
  // 后端字段: garment_file=UploadFile, person_file=UploadFile, prompt=str, model_gender=str

  /// 虚拟试衣：单次请求一张结果；本机 diffusers 首次可能需长时间加载，默认超时 40 分钟。
  Future<Map<String, dynamic>> virtualTryon({
    dynamic garmentImage,
    dynamic personImage,
    String? prompt,
    String modelGender = 'neutral',
    String? garmentCategory,
    Duration timeout = const Duration(seconds: 2400),
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/tryon/garment'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final part = await _multipartImage('garment_file', garmentImage);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }

      if (personImage != null) {
        final part = await _multipartImage('person_file', personImage);
        if (part == null) return {'error': 'Unsupported person image type'};
        request.files.add(part);
      }

      request.fields['model_gender'] = modelGender;
      if (prompt != null && prompt.trim().isNotEmpty) {
        request.fields['prompt'] = prompt.trim();
      }
      if (garmentCategory != null && garmentCategory.trim().isNotEmpty) {
        request.fields['garment_category'] = garmentCategory.trim();
      }

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {
          'error': '未登录或登录已过期，请重新登录后再试',
        };
      }
      var errMsg = 'Virtual try-on failed with status: ${response.statusCode}';
      String? errCode;
      bool? retryable;
      try {
        final body = _parseFastApiErrorBodyMap(response.body);
        if (body != null) {
          errMsg = body['message']?.toString() ?? errMsg;
          errCode = body['error_code']?.toString();
          final rb = body['retryable'];
          if (rb is bool) retryable = rb;
        }
      } catch (_) {}
      return {
        'error': errMsg,
        if (errCode != null) 'error_code': errCode,
        if (retryable != null) 'retryable': retryable,
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// 方案 A 预检：只评估输入质量，不生成试衣图。
  Future<Map<String, dynamic>> tryonV2ValidateInput({
    dynamic garmentImage,
    dynamic personImage,
    String garmentCategory = 'bottom',
    String mode = 'strict',
    Duration timeout = const Duration(seconds: 60),
  }) async {
    try {
      final v2Base = _resolveV2BaseUrl();
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$v2Base/tryon/validate-input'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final part = await _multipartImage('garment_file', garmentImage);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }

      if (personImage != null) {
        final part = await _multipartImage('person_file', personImage);
        if (part == null) return {'error': 'Unsupported person image type'};
        request.files.add(part);
      }

      if (garmentCategory.trim().isNotEmpty) {
        request.fields['garment_category'] = garmentCategory.trim();
      }
      request.fields['mode'] = mode;

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }

      final body = _parseFastApiErrorBodyMap(response.body);
      if (body != null) {
        return {
          'error': body['message']?.toString() ??
              'Try-on precheck failed with status: ${response.statusCode}',
          if (body['error_code'] != null) 'error_code': body['error_code'],
          if (body['retryable'] != null) 'retryable': body['retryable'],
          if (body['action_hint'] != null) 'action_hint': body['action_hint'],
          if (body['qc_scores'] is Map) 'qc_scores': body['qc_scores'],
        };
      }

      return {
        'error': 'Try-on precheck failed with status: ${response.statusCode}'
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// 方案 A 生成：/api/v2/tryon/pants。
  Future<Map<String, dynamic>> virtualTryonV2Pants({
    dynamic garmentImage,
    dynamic personImage,
    String? prompt,
    String modelGender = 'neutral',
    String garmentCategory = 'bottom',
    String mode = 'strict',
    Duration timeout = const Duration(seconds: 2400),
  }) async {
    try {
      final v2Base = _resolveV2BaseUrl();
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$v2Base/tryon/pants'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final part = await _multipartImage('garment_file', garmentImage);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }

      if (personImage != null) {
        final part = await _multipartImage('person_file', personImage);
        if (part == null) return {'error': 'Unsupported person image type'};
        request.files.add(part);
      }

      request.fields['model_gender'] = modelGender;
      request.fields['mode'] = mode;
      if (prompt != null && prompt.trim().isNotEmpty) {
        request.fields['prompt'] = prompt.trim();
      }
      if (garmentCategory.trim().isNotEmpty) {
        request.fields['garment_category'] = garmentCategory.trim();
      }

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {
          'error': '未登录或登录已过期，请重新登录后再试',
        };
      }

      var errMsg =
          'Virtual try-on v2 failed with status: ${response.statusCode}';
      String? errCode;
      bool? retryable;
      String? actionHint;
      try {
        final body = _parseFastApiErrorBodyMap(response.body);
        if (body != null) {
          errMsg = body['message']?.toString() ?? errMsg;
          errCode = body['error_code']?.toString();
          final rb = body['retryable'];
          if (rb is bool) retryable = rb;
          actionHint = body['action_hint']?.toString();
        }
      } catch (_) {}
      return {
        'error': errMsg,
        if (errCode != null) 'error_code': errCode,
        if (retryable != null) 'retryable': retryable,
        if (actionHint != null) 'action_hint': actionHint,
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// v2 统一试衣：/api/v2/tryon/garment（支持 top/bottom/skirt/outfit）。
  Future<Map<String, dynamic>> virtualTryonV2Garment({
    dynamic garmentImage,
    dynamic garmentImage2,
    dynamic personImage,
    String? garmentImageUrl,
    String? garmentImageUrl2,
    String? prompt,
    String modelGender = 'neutral',
    String garmentCategory = 'auto',
    String garmentCategory2 = 'bottom',
    String mode = 'strict',
    Duration timeout = const Duration(seconds: 2400),
  }) async {
    try {
      final v2Base = _resolveV2BaseUrl();
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$v2Base/tryon/garment'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final part = await _multipartImage('garment_file', garmentImage);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }
      if (garmentImage2 != null) {
        final part = await _multipartImage('garment_file_2', garmentImage2);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }
      if (personImage != null) {
        final part = await _multipartImage('person_file', personImage);
        if (part == null) return {'error': 'Unsupported person image type'};
        request.files.add(part);
      }

      request.fields['model_gender'] = modelGender;
      request.fields['mode'] = mode;
      request.fields['garment_category'] = garmentCategory;
      request.fields['garment_category_2'] = garmentCategory2;
      if (garmentImageUrl != null && garmentImageUrl.trim().isNotEmpty) {
        request.fields['garment_image_url'] = garmentImageUrl.trim();
      }
      if (garmentImageUrl2 != null && garmentImageUrl2.trim().isNotEmpty) {
        request.fields['garment_image_url_2'] = garmentImageUrl2.trim();
      }
      if (prompt != null && prompt.trim().isNotEmpty) {
        request.fields['prompt'] = prompt.trim();
      }

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': '未登录或登录已过期，请重新登录后再试'};
      }
      var errMsg =
          'Virtual try-on v2 failed with status: ${response.statusCode}';
      String? errCode;
      bool? retryable;
      String? actionHint;
      try {
        final body = _parseFastApiErrorBodyMap(response.body);
        if (body != null) {
          errMsg = body['message']?.toString() ?? errMsg;
          errCode = body['error_code']?.toString();
          final rb = body['retryable'];
          if (rb is bool) retryable = rb;
          actionHint = body['action_hint']?.toString();
        }
      } catch (_) {}
      return {
        'error': errMsg,
        if (errCode != null) 'error_code': errCode,
        if (retryable != null) 'retryable': retryable,
        if (actionHint != null) 'action_hint': actionHint,
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// v2 预处理：去背景白底 + 自动品类识别。
  Future<Map<String, dynamic>> tryonV2Preprocess({
    dynamic garmentImage,
    Duration timeout = const Duration(seconds: 90),
  }) async {
    try {
      final v2Base = _resolveV2BaseUrl();
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$v2Base/tryon/preprocess'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final part = await _multipartImage('garment_file', garmentImage);
        if (part == null) return {'error': 'Unsupported garment image type'};
        request.files.add(part);
      }

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': '未登录或登录已过期，请重新登录后再试'};
      }
      final body = _parseFastApiErrorBodyMap(response.body);
      if (body != null) {
        return {
          'error': body['message']?.toString() ??
              'Try-on preprocess failed with status: ${response.statusCode}',
          if (body['error_code'] != null) 'error_code': body['error_code'],
          if (body['retryable'] != null) 'retryable': body['retryable'],
          if (body['action_hint'] != null) 'action_hint': body['action_hint'],
        };
      }
      return {
        'error': 'Try-on preprocess failed with status: ${response.statusCode}'
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  // ─── 智能穿搭：天气 + 参考图 + 情绪 ─────────────────────────────
  // 后端: GET /smart-outfit/weather, GET /smart-outfit/weather-by-city
  // POST /smart-outfit/upload-reference, POST /smart-outfit/generate

  Future<Map<String, dynamic>> getSmartOutfitWeather(
      double latitude, double longitude) async {
    try {
      final uri =
          Uri.parse('$baseUrl/smart-outfit/weather').replace(queryParameters: {
        'latitude': latitude.toString(),
        'longitude': longitude.toString(),
      });
      final response = await http
          .get(uri, headers: _jsonHeaders)
          .timeout(const Duration(seconds: 25));
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': 'Could not validate credentials'};
      }
      return {'error': 'Weather failed: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> getSmartOutfitWeatherByCity(String name) async {
    try {
      final uri = Uri.parse('$baseUrl/smart-outfit/weather-by-city')
          .replace(queryParameters: {'name': name.trim()});
      final response = await http
          .get(uri, headers: _jsonHeaders)
          .timeout(const Duration(seconds: 25));
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': 'Could not validate credentials'};
      }
      return {'error': 'City weather failed: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> uploadSmartOutfitReference(
      dynamic imageFile) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/smart-outfit/upload-reference'),
      );
      request.headers.addAll(_authHeaders);
      final part = await _multipartImage('file', imageFile);
      if (part == null) return {'error': 'Unsupported image type'};
      request.files.add(part);
      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 120),
          );
      final response = await http.Response.fromStream(streamedResponse);
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': 'Could not validate credentials'};
      }
      final errMap = _parseFastApiErrorBodyMap(response.body);
      if (errMap != null) {
        return {
          'error': errMap['message']?.toString() ?? 'Upload failed',
          if (errMap['error_code'] != null) 'error_code': errMap['error_code'],
          if (errMap['retryable'] != null) 'retryable': errMap['retryable'],
        };
      }
      return {'error': 'Upload failed: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> generateSmartOutfit({
    required String imageUrl,
    required String location,
    String city = '',
    Map<String, String>? address,
    required String weather,
    required double temperature,
    String mood = '',
    int count = 3,
    int regenerationIndex = 0,
    double? genderExpression,
  }) async {
    final loc = location.trim();
    final moodNorm = _normalizeSmartOutfitMood(mood);
    final body = <String, dynamic>{
      'image_url': imageUrl,
      'location': loc,
      'city': city.trim().isNotEmpty ? city.trim() : loc,
      if (address != null) 'address': address,
      'weather': weather,
      'temperature': temperature,
      'mood': moodNorm,
      'count': count,
      'regeneration_index': regenerationIndex,
    };
    if (genderExpression != null) {
      body['gender_expression'] = genderExpression;
    }
    final genUri = Uri.parse(
      '${baseUrl.replaceAll(RegExp(r'/$'), '')}/smart-outfit/generate',
    );
    final genHeaders = <String, String>{
      ..._jsonHeaders,
      'Content-Type': 'application/json; charset=utf-8',
    };
    try {
      final response = await http
          .post(
            genUri,
            headers: genHeaders,
            body: utf8.encode(json.encode(body)),
          )
          .timeout(const Duration(seconds: 180));
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map && unwrapped['error'] != null) {
          return {'error': unwrapped['error'].toString()};
        }
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      if (response.statusCode == 401) {
        return {'error': 'Could not validate credentials'};
      }
      final errMap = _parseFastApiErrorBodyMap(response.body);
      if (errMap != null) {
        return {
          'error': errMap['message']?.toString() ?? 'Generate failed',
          if (errMap['error_code'] != null) 'error_code': errMap['error_code'],
          if (errMap['retryable'] != null) 'retryable': errMap['retryable'],
        };
      }
      return {'error': 'Generate failed: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// FastAPI 422/500 等返回的 JSON `detail` 字段。
  String? _parseFastApiErrorBody(String body) {
    if (body.isEmpty) return null;
    try {
      final decoded = json.decode(body);
      if (decoded is Map) {
        if (decoded['detail'] != null) {
          return decoded['detail'].toString();
        }
        final error = decoded['error'];
        if (error is Map && error['message'] != null) {
          return error['message'].toString();
        }
        if (decoded['message'] != null) {
          return decoded['message'].toString();
        }
      }
    } catch (_) {}
    return null;
  }

  Map<String, dynamic>? _parseFastApiErrorBodyMap(String body) {
    if (body.isEmpty) return null;
    try {
      final decoded = json.decode(body);
      if (decoded is! Map) return null;

      dynamic detail = decoded['detail'];
      if (detail is String) {
        return {'message': detail};
      }
      if (detail is Map) {
        final m = Map<String, dynamic>.from(detail as Map);
        final nestedDetails = m['details'];
        return {
          'message': m['message']?.toString() ?? m.toString(),
          if (m['error_code'] != null) 'error_code': m['error_code'].toString(),
          if (m['retryable'] is bool) 'retryable': m['retryable'],
          if (m['action_hint'] != null)
            'action_hint': m['action_hint'].toString(),
          if (m['qc_scores'] is Map) 'qc_scores': m['qc_scores'],
          if (nestedDetails is Map && nestedDetails['qc_scores'] is Map)
            'qc_scores': nestedDetails['qc_scores'],
          if (nestedDetails is Map && nestedDetails['action_hint'] != null)
            'action_hint': nestedDetails['action_hint'].toString(),
        };
      }

      final error = decoded['error'];
      if (error is Map && error['message'] != null) {
        final details = error['details'];
        return {
          'message': error['message'].toString(),
          if (error['error_code'] != null)
            'error_code': error['error_code'].toString(),
          if (error['retryable'] is bool) 'retryable': error['retryable'],
          if (error['action_hint'] != null)
            'action_hint': error['action_hint'].toString(),
          if (error['qc_scores'] is Map) 'qc_scores': error['qc_scores'],
          if (details is Map && details['qc_scores'] is Map)
            'qc_scores': details['qc_scores'],
          if (details is Map && details['action_hint'] != null)
            'action_hint': details['action_hint'].toString(),
        };
      }
      if (decoded['message'] != null) {
        return {'message': decoded['message'].toString()};
      }
    } catch (_) {}
    return null;
  }

  // ─── Subscription / Usage ───────────────────────────────────

  Future<Map<String, dynamic>> getSubscriptionStatus() async {
    return get('/subscription/status');
  }

  Future<Map<String, dynamic>> createSubscriptionOrder({
    String tier = 'pro',
  }) async {
    return post('/subscription/order', {'tier': tier});
  }

  Future<Map<String, dynamic>> verifySubscriptionPayment({
    required String orderId,
    required String paymentId,
    required String signature,
  }) async {
    return post('/subscription/verify', {
      'order_id': orderId,
      'payment_id': paymentId,
      'signature': signature,
    });
  }

  Future<Map<String, dynamic>> consumeUsage({
    required String action,
    int units = 1,
  }) async {
    return post('/usage/consume', {
      'action': action,
      'units': units,
    });
  }

  Future<Map<String, dynamic>> getUsageStatus({
    required String action,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl/usage/status')
          .replace(queryParameters: {'action': action});
      final response = await http.get(uri, headers: _jsonHeaders);
      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final unwrapped = unwrapApiResponseEnvelope(decoded);
        if (unwrapped is Map) return Map<String, dynamic>.from(unwrapped);
        return {'data': unwrapped};
      }
      final errMap = _parseFastApiErrorBodyMap(response.body);
      if (errMap != null) return {'error': errMap['message'].toString()};
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }
}
