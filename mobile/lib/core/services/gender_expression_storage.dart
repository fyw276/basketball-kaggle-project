import 'package:shared_preferences/shared_preferences.dart';

class GenderExpressionStorage {
  static const String _key = 'gender_expression';

  static Future<double> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getDouble(_key) ?? 0.5;
    } catch (e) {
      return 0.5;
    }
  }

  static Future<void> save(double value) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setDouble(_key, value);
    } catch (e) {
      // Ignore errors
    }
  }
}
