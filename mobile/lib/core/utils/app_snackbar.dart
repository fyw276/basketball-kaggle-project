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
  if (s.contains('Connection refused')) {
    return '无法连接服务器，请检查网络后重试';
  }
  if (s.contains('ClientException')) {
    final low = s.toLowerCase();
    if (low.contains('connection') ||
        low.contains('failed') ||
        low.contains('closed') ||
        low.contains('socket')) {
      return '无法连接服务器，请检查网络后重试';
    }
  }
  if (s.length > 160) {
    return '${s.substring(0, 157)}…';
  }
  return s;
}

/// 统一时长与样式，避免遗漏 [SnackBar.duration] 导致 Web 后台标签页下体验异常。
///
/// 自 Flutter 3.41 起，带 [SnackBarAction] 时默认 [SnackBar.persist] 为 `true`，
/// 会忽略 [SnackBar.duration] 直到用户点击操作。此处显式 [persist]：`false` 表示
/// 仍按 [duration] 自动消失；用户在超时前仍可点击 action。
void showAppSnackBar(
  BuildContext context,
  String message, {
  Color? backgroundColor,
  SnackBarAction? action,
  SnackBarBehavior behavior = SnackBarBehavior.floating,
  Duration duration = kAppSnackBarDuration,

  /// `false`：到点自动关闭（有 action 时仍如此，除非无障碍长时间播报等特殊逻辑）。
  bool persist = false,
}) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      duration: duration,
      persist: persist,
      behavior: behavior,
      backgroundColor: backgroundColor,
      action: action,
    ),
  );
}
