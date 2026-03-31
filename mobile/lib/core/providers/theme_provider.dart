import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../theme/fashion_palettes.dart';
import '../services/gender_expression_storage.dart';

/// 性别枚举（保留以兼容旧代码）
enum UserGender { none, male, female }

/// 全局主题 + 性别表达指数状态管理器。
/// 拖动性别表达滑块时自动切换配色（三段：偏男 0~0.3 / 中性 0.3~0.7 / 偏女 0.7~1）。
class ThemeProvider extends ChangeNotifier {
  ThemeMode _themeMode = ThemeMode.system;
  bool _isInitialized = false;
  double _genderExpression = 0.5;
  late Palette _palette;
  UserGender _style = UserGender.none; // 兼容旧代码

  ThemeProvider() {
    _palette = FashionPalettes.fromGenderExpression(_genderExpression);
    _loadGenderExpression();
  }

  Future<void> _loadGenderExpression() async {
    _genderExpression = await GenderExpressionStorage.load();
    _palette = FashionPalettes.fromGenderExpression(_genderExpression);
    _isInitialized = true;
    notifyListeners();
  }

  // ─── Getters ────────────────────────────────────────────────────────
  ThemeMode get themeMode => _themeMode;
  bool get isInitialized => _isInitialized;
  Palette get palette => _palette;
  double get genderExpression => _genderExpression;
  UserGender get style => _style; // 兼容旧代码

  ThemeData get lightTheme => AppTheme.buildThemeDataFromPalette(_palette);
  ThemeData get darkTheme => AppTheme.darkTheme;
  bool get isDarkMode => _themeMode == ThemeMode.dark;

  String get genderExpressionLabel =>
      FashionPalettes.genderLabel(_genderExpression);

  // ─── Setters ───────────────────────────────────────────────────────

  void setThemeMode(ThemeMode mode) {
    _themeMode = mode;
    notifyListeners();
  }

  void toggleTheme() {
    _themeMode =
        _themeMode == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    notifyListeners();
  }

  /// 性别表达指数变更 → 同步切换全局配色（无延迟）。
  void setGenderExpression(double value) {
    _genderExpression = value.clamp(0.0, 1.0);
    _palette = FashionPalettes.fromGenderExpression(_genderExpression);
    GenderExpressionStorage.save(_genderExpression);
    notifyListeners();
  }

  /// 兼容旧代码：根据 UserGender 推断性别表达指数（仅影响 _style）
  void setStyle(UserGender gender) {
    switch (gender) {
      case UserGender.male:
        _genderExpression = 0.15;
        break;
      case UserGender.female:
        _genderExpression = 0.85;
        break;
      case UserGender.none:
        _genderExpression = 0.5;
        break;
    }
    _style = gender;
    _palette = FashionPalettes.fromGenderExpression(_genderExpression);
    notifyListeners();
  }
}
