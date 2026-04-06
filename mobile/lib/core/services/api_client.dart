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

class ApiClient {
  final String baseUrl;
  String? _token;

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
        return json.decode(response.body);
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<dynamic> getList(String path) async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
      );
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
      return [];
    } catch (e) {
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
        return json.decode(response.body);
      }
      if (response.statusCode == 404) {
        return {
          'error': 'Request failed with status: 404 ($uri)。'
              '请确认已启动本仓库后端且端口一致（默认 8010，见 backend/.env 的 PORT）。'
              '浏览器打开 http://127.0.0.1:<端口>/ 应返回 Smart Outfit Assistant。',
        };
      }
      return {
        'error': 'Request failed with status: ${response.statusCode} ($uri)',
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  /// AI 穿搭风格分：`POST /predict`（默认 `127.0.0.1:8765`，与 `backend.main` 一致）。
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
        return json.decode(response.body) as Map<String, dynamic>;
      }
      final errBody = response.body.isNotEmpty
          ? json.decode(response.body)
          : <String, dynamic>{};
      final detail = errBody['detail'];
      final msg = detail is String
          ? detail
          : 'Request failed with status: ${response.statusCode} ($uri)';
      return {'error': msg};
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
        return json.decode(response.body) as Map<String, dynamic>;
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
        return json.decode(response.body) as Map<String, dynamic>;
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  // ─── Auth ──────────────────────────────────────────────────────

  Future<Map<String, dynamic>> register(
      String username, String email, String password) async {
    return post('/auth/register', {
      'username': username,
      'email': email,
      'password': password,
    });
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
        if (decoded is Map) return decoded.cast<String, dynamic>();
        return {'data': decoded};
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
  }) async {
    final params = <String>[];
    if (category != null) params.add('category=$category');
    if (color != null) params.add('color=$color');
    if (style != null) params.add('style=$style');
    final query = params.isNotEmpty ? '?${params.join('&')}' : '';

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
        return json.decode(response.body);
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
        return json.decode(response.body);
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
        return json.decode(response.body);
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
        return json.decode(response.body);
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

  /// 虚拟试衣：CPU 扩散常超过 3 分钟，默认单次超时 15 分钟；页面会连发 3 次（正/侧/背）。
  Future<Map<String, dynamic>> virtualTryon({
    dynamic garmentImage,
    dynamic personImage,
    String? prompt,
    String modelGender = 'neutral',
    Duration timeout = const Duration(seconds: 900),
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

      final streamedResponse = await request.send().timeout(timeout);
      final response =
          await http.Response.fromStream(streamedResponse).timeout(timeout);

      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
      if (response.statusCode == 401) {
        return {
          'error': '未登录或登录已过期，请重新登录后再试',
        };
      }
      var errMsg = 'Virtual try-on failed with status: ${response.statusCode}';
      try {
        final body = json.decode(response.body);
        if (body is Map && body['detail'] != null) {
          errMsg = body['detail'].toString();
        }
      } catch (_) {}
      return {'error': errMsg};
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
        return json.decode(response.body) as Map<String, dynamic>;
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
        return json.decode(response.body) as Map<String, dynamic>;
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
        return json.decode(response.body) as Map<String, dynamic>;
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
        if (decoded is Map) {
          return Map<String, dynamic>.from(decoded);
        }
        return {'error': '响应格式错误'};
      }
      final err = _parseFastApiErrorBody(response.body);
      if (err != null) return {'error': err};
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
      if (decoded is Map && decoded['detail'] != null) {
        return decoded['detail'].toString();
      }
    } catch (_) {}
    return null;
  }
}
