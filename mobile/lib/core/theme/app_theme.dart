import 'package:flutter/material.dart';
import 'fashion_palettes.dart';

class AppTheme {
  AppTheme._();

  static const List<String> _fontFallback = [
    'Noto Sans CJK SC',
    'Noto Sans SC',
    'Microsoft YaHei',
    'Microsoft YaHei UI',
    'PingFang SC',
    'Hiragino Sans GB',
    'Source Han Sans SC',
    'SimHei',
    'Arial Unicode MS',
  ];

  static TextStyle? _fallbackTextStyle(TextStyle? style) =>
      style?.copyWith(fontFamilyFallback: _fontFallback);

  static TextTheme _withChineseFallback(TextTheme base) {
    return base.copyWith(
      displayLarge: _fallbackTextStyle(base.displayLarge),
      displayMedium: _fallbackTextStyle(base.displayMedium),
      displaySmall: _fallbackTextStyle(base.displaySmall),
      headlineLarge: _fallbackTextStyle(base.headlineLarge),
      headlineMedium: _fallbackTextStyle(base.headlineMedium),
      headlineSmall: _fallbackTextStyle(base.headlineSmall),
      titleLarge: _fallbackTextStyle(base.titleLarge),
      titleMedium: _fallbackTextStyle(base.titleMedium),
      titleSmall: _fallbackTextStyle(base.titleSmall),
      bodyLarge: _fallbackTextStyle(base.bodyLarge),
      bodyMedium: _fallbackTextStyle(base.bodyMedium),
      bodySmall: _fallbackTextStyle(base.bodySmall),
      labelLarge: _fallbackTextStyle(base.labelLarge),
      labelMedium: _fallbackTextStyle(base.labelMedium),
      labelSmall: _fallbackTextStyle(base.labelSmall),
    );
  }

  /// 从 Palette（三段配色）构建 ThemeData。
  static ThemeData buildThemeDataFromPalette(Palette p) {
    final baseTextTheme = _withChineseFallback(Typography.material2021().black);
    return ThemeData(
      useMaterial3: true,
      fontFamilyFallback: _fontFallback,
      textTheme: baseTextTheme,
      primaryTextTheme: _withChineseFallback(Typography.material2021().black),
      colorScheme: ColorScheme.fromSeed(
        seedColor: p.primary,
        brightness: Brightness.light,
        primary: p.primary,
        secondary: p.secondary,
        surface: p.surface,
        onSurface: p.textTitle,
        error: p.deleteColor,
      ),
      scaffoldBackgroundColor: p.background,
      appBarTheme: AppBarTheme(
        backgroundColor: p.background,
        foregroundColor: p.textTitle,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: true,
      ),
      cardTheme: CardThemeData(
        color: p.cardBg,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22),
          side: BorderSide(color: p.divider),
        ),
      ),
      dividerTheme: DividerThemeData(color: p.divider, thickness: 1),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: p.primary,
        foregroundColor: Colors.white,
        elevation: 4,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(18)),
        filled: true,
        fillColor: p.searchBg,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: p.chipUnselectedBg,
        selectedColor: p.chipSelectedBg,
        labelStyle: TextStyle(
          color: p.textTitle,
          fontFamilyFallback: _fontFallback,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: p.surface,
        indicatorColor: p.primary.withValues(alpha: 0.18),
        surfaceTintColor: Colors.transparent,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return TextStyle(
              color: p.primary,
              fontWeight: FontWeight.w700,
              fontSize: 12,
              fontFamilyFallback: _fontFallback,
            );
          }
          return TextStyle(
            color: p.textBody,
            fontSize: 12,
            fontFamilyFallback: _fontFallback,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return IconThemeData(color: p.primary);
          }
          return IconThemeData(color: p.textBody);
        }),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: p.primary,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          minimumSize: const Size(0, 52),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(26)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: p.primary),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: p.primary,
          side: BorderSide(color: p.primary),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(26)),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  static ThemeData get lightTheme =>
      buildThemeDataFromPalette(FashionPalettes.fromGenderExpression(0.5));
  static ThemeData get darkTheme => ThemeData(
        useMaterial3: true,
        fontFamilyFallback: _fontFallback,
        textTheme: _withChineseFallback(Typography.material2021().white),
        primaryTextTheme: _withChineseFallback(Typography.material2021().white),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6366F1),
          brightness: Brightness.dark,
        ),
        snackBarTheme: const SnackBarThemeData(
          behavior: SnackBarBehavior.floating,
        ),
      );
}
