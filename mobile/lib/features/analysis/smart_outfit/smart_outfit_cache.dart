import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Local persistence for smart outfit weather row + home recommendation cache.
class SmartOutfitWeatherCache {
  static const _kFullAddress = 'smart_outfit_full_address';
  static const _kCityShort = 'smart_outfit_city_short';
  static const _kWeather = 'smart_outfit_weather';
  static const _kTemp = 'smart_outfit_temp';
  static const _kFallback = 'smart_outfit_fallback';

  static Future<void> persist({
    required String fullAddressLine,
    required String cityShort,
    required String weather,
    required double temp,
    required bool weatherFallback,
  }) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(_kFullAddress, fullAddressLine);
      await p.setString(_kCityShort, cityShort);
      await p.setString(_kWeather, weather);
      await p.setDouble(_kTemp, temp);
      await p.setBool(_kFallback, weatherFallback);
    } catch (_) {}
  }

  /// Returns null when no cache row exists.
  static Future<SmartOutfitWeatherSnapshot?> restore() async {
    try {
      final p = await SharedPreferences.getInstance();
      final fa = p.getString(_kFullAddress);
      if (fa == null || fa.isEmpty) return null;
      return SmartOutfitWeatherSnapshot(
        fullAddressLine: fa,
        displayAddress: fa,
        cityShort: p.getString(_kCityShort) ?? '',
        weather: p.getString(_kWeather) ?? '晴',
        temp: p.getDouble(_kTemp) ?? 20,
        weatherFallback: p.getBool(_kFallback) ?? false,
      );
    } catch (_) {
      return null;
    }
  }
}

class SmartOutfitWeatherSnapshot {
  final String fullAddressLine;
  final String displayAddress;
  final String cityShort;
  final String weather;
  final double temp;
  final bool weatherFallback;

  const SmartOutfitWeatherSnapshot({
    required this.fullAddressLine,
    required this.displayAddress,
    required this.cityShort,
    required this.weather,
    required this.temp,
    required this.weatherFallback,
  });
}

class SmartOutfitHomeRecommendationCache {
  static const _kJson = 'home_today_recommendation';
  static const _kJsonAlt = 'home_today_recommendation_json';

  static Future<void> saveTodayAtIndex({
    required List<Map<String, dynamic>> outfits,
    required int index,
    required String cityShort,
    required String weather,
    required double temp,
  }) async {
    try {
      if (outfits.isEmpty) return;
      final safeIndex = index.clamp(0, outfits.length - 1);
      final outfit = outfits[safeIndex];
      final prefs = await SharedPreferences.getInstance();
      final ai = outfit['ai_recommendation'];
      final payload = {
        'city': cityShort,
        'weather': weather,
        'temperature': temp,
        'recommendation_index': safeIndex,
        'updated_at': DateTime.now().toIso8601String(),
        'description': outfit['description']?.toString() ?? '',
        'preview_image_url': outfit['preview_image_url']?.toString() ?? '',
        'ai_recommendation': ai is Map ? Map<String, dynamic>.from(ai) : {},
      };
      final enc = jsonEncode(payload);
      await prefs.setString(_kJson, enc);
      await prefs.setString(_kJsonAlt, enc);
    } catch (_) {}
  }
}
