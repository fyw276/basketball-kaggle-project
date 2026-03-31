import 'package:flutter/material.dart';
import '../providers/theme_provider.dart';

class StyleTokens {
  final Color primary;
  final Color accent;
  final Color surface;
  final Color surface2;
  final Color border;
  final Color text;
  final Color muted;
  final int style;

  const StyleTokens({
    required this.primary,
    required this.accent,
    required this.surface,
    required this.surface2,
    required this.border,
    required this.text,
    required this.muted,
    required this.style,
  });

  static StyleTokens fromStyle(UserGender gender) {
    switch (gender) {
      case UserGender.male:
        return const StyleTokens(
          primary: Color(0xFF3B82F6),
          accent: Color(0xFF6366F1),
          surface: Color(0xFFF1F5F9),
          surface2: Color(0xFFE2E8F0),
          border: Color(0xFFCBD5E1),
          text: Color(0xFF1E293B),
          muted: Color(0xFF64748B),
          style: 0,
        );
      case 1:
        return const StyleTokens(
          primary: Color(0xFFEC4899),
          accent: Color(0xFFF472B6),
          surface: Color(0xFFFDF2F8),
          surface2: Color(0xFFFCE7F3),
          border: Color(0xFFF9A8D4),
          text: Color(0xFF831843),
          muted: Color(0xFFBE185D),
          style: 1,
        );
      default:
        return const StyleTokens(
          primary: Color(0xFF6366F1),
          accent: Color(0xFF8B5CF6),
          surface: Color(0xFFF8FAFC),
          surface2: Color(0xFFF1F5F9),
          border: Color(0xFFE2E8F0),
          text: Color(0xFF1E293B),
          muted: Color(0xFF64748B),
          style: 2,
        );
    }
  }

  List<BoxShadow> cardShadow() {
    return [
      BoxShadow(
        color: primary.withValues(alpha: 0.08),
        blurRadius: 16,
        offset: const Offset(0, 4),
      ),
    ];
  }

  TextStyle get titleStyle =>
      TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: text);
  double get cardRadius => 16.0;
  double get cardRadiusSm => 12.0;
  double get pageMaxWidth => 600.0;
  TextStyle get subtitleStyle =>
      TextStyle(fontSize: 14, fontWeight: FontWeight.w400, color: muted);
  TextStyle get bodyStyle =>
      TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: text);

  LinearGradient pageGradient() {
    return LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [surface, surface2],
    );
  }

  Color get bg1 => surface;
  Color get bg2 => surface2;
  BackgroundArtKind get art => BackgroundArtKind.minimal;
}

enum BackgroundArtKind { forest, neo, minimal }
