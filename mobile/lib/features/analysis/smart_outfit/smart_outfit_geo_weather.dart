import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

/// GPS + weather UX helpers (no [BuildContext]).
class SmartOutfitGeo {
  static LocationSettings gpsLocationSettings({bool preferFresh = true}) {
    if (kIsWeb) {
      return WebSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 0,
        timeLimit: const Duration(seconds: 25),
        maximumAge: preferFresh
            ? const Duration(seconds: 2)
            : const Duration(seconds: 45),
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 0,
      timeLimit: Duration(seconds: 20),
    );
  }

  static bool poorAccuracy(Position p) {
    final a = p.accuracy;
    return a.isNaN || a <= 0 || a > 500;
  }

  static Future<Position> currentPositionWithRetry() async {
    Object? last;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final p = await Geolocator.getCurrentPosition(
          locationSettings: gpsLocationSettings(preferFresh: true),
        );
        if (attempt == 0 && poorAccuracy(p)) {
          await Future.delayed(const Duration(milliseconds: 900));
          final p2 = await Geolocator.getCurrentPosition(
            locationSettings: gpsLocationSettings(preferFresh: true),
          );
          return poorAccuracy(p2) ? p : p2;
        }
        return p;
      } catch (e) {
        last = e;
        if (attempt < 1) {
          await Future.delayed(const Duration(milliseconds: 700));
        }
      }
    }
    throw (last ?? StateError('position'));
  }
}

bool smartOutfitHadReliableWeatherSnapshot({
  required bool fallback,
  required String full,
  required String disp,
  required String city,
}) {
  if (fallback) return false;
  if (city.trim() == '默认') return false;
  return full.trim().isNotEmpty ||
      disp.trim().isNotEmpty ||
      city.trim().isNotEmpty;
}

String smartOutfitWeatherFailureHint(Object e) {
  final s = e.toString();
  if (s.contains('401')) {
    return '登录已失效或无效，请重新登录后再试定位与天气';
  }
  if (s.contains('403')) {
    return '没有权限访问天气接口，请检查账号';
  }
  if (s.contains('503') || s.toLowerCase().contains('unavailable')) {
    return '天气服务暂时不可用，请稍后重试';
  }
  return '无法更新位置或天气，仍显示上次定位；或请使用「手动选择地址」';
}

IconData smartOutfitWeatherIcon(String weather) {
  final w = weather;
  if (w.contains('雨') || w.contains('雷')) return Icons.umbrella;
  if (w.contains('雪')) return Icons.ac_unit;
  if (w.contains('云') || w.contains('阴')) {
    return Icons.cloud_outlined;
  }
  return Icons.wb_sunny_outlined;
}
