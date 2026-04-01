import 'package:flutter/material.dart';

/// 应用内 SnackBar 统一约 5 秒后消失（与 [SnackBarThemeData] 一致）。
const Duration kAppSnackBarDuration = Duration(seconds: 5);

/// 将接口/异常转为简短可读文案，避免长串 Timeout 撑满屏幕。
String userFacingApiError(Object? error) {
  final s = error?.toString() ?? '未知错误';
  if (s.contains('TimeoutException') || s.toLowerCase().contains('timeout')) {
    return '请求超时，请确认后端已启动或稍后重试';
  }
  if (s.contains('SocketException') ||
      s.contains('Failed host lookup') ||
      s.contains('Network is unreachable')) {
    return '网络异常，请检查连接';
  }
  if (s.contains('Connection refused') || s.contains('ClientException')) {
    return '无法连接服务器，请检查接口地址与后端';
  }
  if (s.length > 160) {
    return '${s.substring(0, 157)}…';
  }
  return s;
}

/// 统一时长与样式，避免遗漏 [SnackBar.duration] 导致 Web 后台标签页下体验异常。
void showAppSnackBar(
  BuildContext context,
  String message, {
  Color? backgroundColor,
  SnackBarAction? action,
  SnackBarBehavior behavior = SnackBarBehavior.floating,
}) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      duration: kAppSnackBarDuration,
      behavior: behavior,
      backgroundColor: backgroundColor,
      action: action,
    ),
  );
}
