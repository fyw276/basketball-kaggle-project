import 'package:flutter/material.dart';

enum AppThemeType { male, female, universal }

extension AppThemeTypeExtension on AppThemeType {
  static AppThemeType fromGender(int gender) {
    switch (gender) {
      case 0:
        return AppThemeType.male;
      case 1:
        return AppThemeType.female;
      default:
        return AppThemeType.universal;
    }
  }
}

class ThemeColors {
  final Color primary;
  final Color accent;
  final Color surface;
  final Color surfaceVariant;
  final String name;

  const ThemeColors({
    required this.primary,
    required this.accent,
    required this.surface,
    required this.surfaceVariant,
    required this.name,
  });

  static ThemeColors fromGender(int gender) {
    switch (gender) {
      case 0:
        return const ThemeColors(
          primary: Color(0xFF3B82F6),
          accent: Color(0xFF6366F1),
          surface: Color(0xFFF1F5F9),
          surfaceVariant: Color(0xFFE2E8F0),
          name: '男生风格',
        );
      case 1:
        return const ThemeColors(
          primary: Color(0xFFEC4899),
          accent: Color(0xFFF472B6),
          surface: Color(0xFFFDF2F8),
          surfaceVariant: Color(0xFFFCE7F3),
          name: '女生风格',
        );
      default:
        return const ThemeColors(
          primary: Color(0xFF6366F1),
          accent: Color(0xFF8B5CF6),
          surface: Color(0xFFF8FAFC),
          surfaceVariant: Color(0xFFF1F5F9),
          name: '中性风格',
        );
    }
  }
}
