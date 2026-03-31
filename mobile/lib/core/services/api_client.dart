import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';

class ApiClient {
  final String baseUrl;
  String? _token;

  ApiClient({this.baseUrl = 'http://127.0.0.1:8000/api/v1'});

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

  // ─── 工具方法 ───────────────────────────────────────────────────

  /// 解析多种图片类型，返回本地路径字符串
  String? _resolvePath(dynamic imageFile) {
    if (imageFile == null) return null;
    if (imageFile is XFile) return imageFile.path;
    if (imageFile is File) return imageFile.path;
    if (imageFile is String) return imageFile;
    return null;
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
    try {
      final response = await http.post(
        Uri.parse('$baseUrl$path'),
        headers: _jsonHeaders,
        body: json.encode(data),
      );
      if (response.statusCode == 200 || response.statusCode == 201) {
        return json.decode(response.body);
      }
      return {'error': 'Request failed with status: ${response.statusCode}'};
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
      if (response.statusCode == 200) {
        return json.decode(response.body);
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
      if (response.statusCode == 200) {
        return json.decode(response.body);
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
        final path = _resolvePath(imageFile);
        if (path == null) {
          return {'error': 'Unsupported image type: ${imageFile.runtimeType}'};
        }
        request.files.add(await http.MultipartFile.fromPath(
          'file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
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
    return delete('/wardrobe/simple/garments/$garmentId/');
  }

  Future<Map<String, dynamic>> updateGarmentCategory(
      String garmentId, String category) async {
    return patch(
        '/wardrobe/simple/garments/$garmentId/', {'category': category});
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
        final path = _resolvePath(imageFile);
        if (path == null) return {'error': 'Unsupported image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
      }

      request.fields['save'] = save.toString();
      if (selectedIndexes != null && selectedIndexes.isNotEmpty) {
        request.fields['selected_indexes'] = selectedIndexes.join(',');
      }

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 60),
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
        final path = _resolvePath(imageFile);
        if (path == null) return {'error': 'Unsupported image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
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
  // 后端字段: file=UploadFile, num_outfits=int, gender_expression=Optional[float], scene=Optional[str]

  Future<Map<String, dynamic>> recommendOutfits({
    dynamic imageFile,
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

      if (imageFile != null) {
        final path = _resolvePath(imageFile);
        if (path == null) return {'error': 'Unsupported image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
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
        final path = _resolvePath(imageFile);
        if (path == null) return {'error': 'Unsupported image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
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
  // 后端字段: garment_file=UploadFile, person_file=UploadFile, model_gender=str

  Future<Map<String, dynamic>> virtualTryon({
    dynamic garmentImage,
    dynamic personImage,
    int numResults = 3,
  }) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/tryon/garment'),
      );
      request.headers.addAll(_authHeaders);

      if (garmentImage != null) {
        final path = _resolvePath(garmentImage);
        if (path == null) return {'error': 'Unsupported garment image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'garment_file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
      }

      if (personImage != null) {
        final path = _resolvePath(personImage);
        if (path == null) return {'error': 'Unsupported person image type'};
        request.files.add(await http.MultipartFile.fromPath(
          'person_file',
          path,
          contentType: MediaType('image', 'jpeg'),
        ));
      }

      request.fields['model_gender'] = 'neutral';

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 120),
          );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
      return {
        'error': 'Virtual try-on failed with status: ${response.statusCode}'
      };
    } catch (e) {
      return {'error': e.toString()};
    }
  }
}
