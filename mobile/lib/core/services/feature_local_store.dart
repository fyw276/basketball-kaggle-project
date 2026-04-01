import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 各功能页内置本地持久化：非 Web 写入应用文档目录 JSON 文件；Web 使用 SharedPreferences。
class FeatureLocalStore {
  FeatureLocalStore._();

  static const _webPrefix = 'feature_json_';

  static Future<void> saveJson(
      String featureId, Map<String, dynamic> data) async {
    final json = jsonEncode(data);
    if (kIsWeb) {
      final p = await SharedPreferences.getInstance();
      await p.setString('$_webPrefix$featureId', json);
      return;
    }
    final dir = await getApplicationDocumentsDirectory();
    final file = File('${dir.path}/feature_$featureId.json');
    await file.writeAsString(json);
  }

  static Future<Map<String, dynamic>?> loadJson(String featureId) async {
    try {
      if (kIsWeb) {
        final p = await SharedPreferences.getInstance();
        final s = p.getString('$_webPrefix$featureId');
        if (s == null || s.isEmpty) return null;
        final decoded = jsonDecode(s);
        return decoded is Map<String, dynamic> ? decoded : null;
      }
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/feature_$featureId.json');
      if (!await file.exists()) return null;
      final raw = await file.readAsString();
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }
}
