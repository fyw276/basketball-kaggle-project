import 'package:flutter/material.dart';

/// 三段配色（严格色值）：偏男性莫卡蓝 / 中性青色系 / 偏女性莫卡紫。
/// 拖动性别表达滑块时切换，无性别选项绑定。
class FashionPalettes {
  static const double maleThreshold = 0.3;
  static const double femaleThreshold = 0.7;

  static Palette fromGenderExpression(double v) {
    if (v <= maleThreshold) return _male;
    if (v < femaleThreshold) return _neutral;
    return _female;
  }

  // ─── 偏男性风格 0.0～0.3：莫卡蓝系 ─────────────────────────────────
  static const Palette _male = Palette(
    mode: 'male',
    background: Color(0xFFF5F7FA),
    surface: Color(0xFFFFFFFF),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFE2E8F0),
    primary: Color(0xFF6B7F99),
    primaryDark: Color(0xFF5A6B82),
    secondary: Color(0xFF94A7C0),
    accent: Color(0xFF6B7F99),
    textTitle: Color(0xFF1F2937),
    textBody: Color(0xFF4B5563),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFF6B7F99),
    chipUnselectedBg: Color(0xFFEEF2F7),
    cardShadow: Color(0x12000000),
  );

  // ─── 中性风格 0.3～0.7：青色系 ────────────────────────────────────
  static const Palette _neutral = Palette(
    mode: 'neutral',
    background: Color(0xFFF7FAFA),
    surface: Color(0xFFFFFFFF),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFE8F0EF),
    primary: Color(0xFF73A89F),
    primaryDark: Color(0xFF5F8F87),
    secondary: Color(0xFF92C8BC),
    accent: Color(0xFF73A89F),
    textTitle: Color(0xFF1F2937),
    textBody: Color(0xFF4B5563),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFF73A89F),
    chipUnselectedBg: Color(0xFFEAF5F3),
    cardShadow: Color(0x12000000),
  );

  // ─── 偏女性风格 0.7～1.0：莫卡紫系 ─────────────────────────────────
  static const Palette _female = Palette(
    mode: 'female',
    background: Color(0xFFF9F5FB),
    surface: Color(0xFFFFFBFE),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFF0EAF5),
    primary: Color(0xFFA096C2),
    primaryDark: Color(0xFF8B7EAE),
    secondary: Color(0xFFD9A8E5),
    accent: Color(0xFFA096C2),
    textTitle: Color(0xFF1F2937),
    textBody: Color(0xFF4B5563),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFFA096C2),
    chipUnselectedBg: Color(0xFFF3EDFA),
    cardShadow: Color(0x12000000),
  );

  static List<Color> get genderBarGradient => [
        _male.primary,
        _neutral.primary,
        _female.primary,
      ];

  static String genderLabel(double v) {
    if (v <= maleThreshold) return '偏男性风格';
    if (v < femaleThreshold) return '中性风格';
    return '偏女性风格';
  }

  static String genderRange(double v) {
    if (v <= maleThreshold) return '偏男性风格';
    if (v < femaleThreshold) return '中性风格';
    return '偏女性风格';
  }
}

class Palette {
  final String mode;
  final Color background;
  final Color surface;
  final Color cardBg;
  final Color divider;
  final Color primary;
  final Color primaryDark;
  final Color secondary;
  final Color accent;
  final Color textTitle;
  final Color textBody;
  final Color deleteColor;
  final Color successColor;
  final Color chipSelectedBg;
  final Color chipUnselectedBg;
  final Color cardShadow;

  const Palette({
    required this.mode,
    required this.background,
    required this.surface,
    required this.cardBg,
    required this.divider,
    required this.primary,
    required this.primaryDark,
    required this.secondary,
    required this.accent,
    required this.textTitle,
    required this.textBody,
    required this.deleteColor,
    required this.successColor,
    required this.chipSelectedBg,
    required this.chipUnselectedBg,
    required this.cardShadow,
  });

  Color get chipSelectedLabel => Colors.white;
  Color get chipUnselectedLabel => textTitle;
  Color get filledButtonBg => primary;
  Color get filledButtonLabel => Colors.white;
  Color get searchBg => chipUnselectedBg;
  Color get deleteBg => deleteColor;
  Color get undoBarBg => successColor;

  List<BoxShadow> get cardShadows => [
        BoxShadow(
            color: cardShadow, blurRadius: 14, offset: const Offset(0, 4)),
      ];
}
