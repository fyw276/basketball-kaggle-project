import 'package:flutter/material.dart';

/// 三段配色体系：偏男性化(0~0.3) / 中性(0.3~0.7) / 偏女性化(0.7~1)
/// 拖动性别表达滑块时自动切换，无性别绑定。
class FashionPalettes {
  /// 阈值
  static const double maleThreshold = 0.3; // 0.0 ~ 0.3 偏男
  static const double femaleThreshold = 0.7; // 0.7 ~ 1.0 偏女
  // 0.3 ~ 0.7 中性（默认）

  /// 根据 genderExpression 区间返回对应配色。
  static Palette fromGenderExpression(double v) {
    if (v <= maleThreshold) return _male;
    if (v < femaleThreshold) return _neutral;
    return _female;
  }

  // ─── 偏男性化 (0.0 ~ 0.3) ──────────────────────────────────────────
  static const Palette _male = Palette(
    mode: 'male',
    background: Color(0xFFF7F9FC),
    surface: Color(0xFFFFFFFF),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFE2E6EC),
    primary: Color(0xFF7A93AC),
    primaryDark: Color(0xFF5A7A9A),
    secondary: Color(0xFF92BBD9),
    accent: Color(0xFF7A93AC),
    textTitle: Color(0xFF2A2A2A),
    textBody: Color(0xFF555555),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFF7A93AC),
    chipUnselectedBg: Color(0xFFF0F4F8),
    cardShadow: Color(0x0D000000),
  );

  // ─── 中性 (0.3 ~ 0.7) ─────────────────────────────────────────────
  static const Palette _neutral = Palette(
    mode: 'neutral',
    background: Color(0xFFFBFBFC),
    surface: Color(0xFFFFFFFF),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFE8E8ED),
    primary: Color(0xFFA096C2),
    primaryDark: Color(0xFF8A7BB0),
    secondary: Color(0xFF92C8BC),
    accent: Color(0xFFA096C2),
    textTitle: Color(0xFF333333),
    textBody: Color(0xFF666666),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFFA096C2),
    chipUnselectedBg: Color(0xFFF2F0F7),
    cardShadow: Color(0x0D000000),
  );

  // ─── 偏女性化 (0.7 ~ 1.0) ─────────────────────────────────────────
  static const Palette _female = Palette(
    mode: 'female',
    background: Color(0xFFFDFBFD),
    surface: Color(0xFFFFFFFF),
    cardBg: Color(0xFFFFFFFF),
    divider: Color(0xFFEAEAEA),
    primary: Color(0xFFD9A8E5),
    primaryDark: Color(0xFFC080D0),
    secondary: Color(0xFFF8C8DC),
    accent: Color(0xFFD9A8E5),
    textTitle: Color(0xFF333333),
    textBody: Color(0xFF666666),
    deleteColor: Color(0xFFFF8A80),
    successColor: Color(0xFF6BCF7F),
    chipSelectedBg: Color(0xFFD9A8E5),
    chipUnselectedBg: Color(0xFFF5F0F8),
    cardShadow: Color(0x0D000000),
  );

  /// 性别表达滑块渐变色（男 → 中 → 女）
  static List<Color> get genderBarGradient => [
        const Color(0xFF7A93AC),
        const Color(0xFFA096C2),
        const Color(0xFFD9A8E5)
      ];

  /// 滑块标签
  static String genderLabel(double v) {
    if (v <= maleThreshold) return '偏男性化穿搭';
    if (v < femaleThreshold) return '中性穿搭';
    return '偏女性化穿搭';
  }

  /// 区间文字
  static String genderRange(double v) {
    if (v <= maleThreshold) return '偏男性化';
    if (v < femaleThreshold) return '中性';
    return '偏女性化';
  }
}

/// 单套完整配色方案。
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

  /// 卡片柔和阴影
  List<BoxShadow> get cardShadows => [
        BoxShadow(
            color: cardShadow, blurRadius: 12, offset: const Offset(0, 2)),
      ];
}
