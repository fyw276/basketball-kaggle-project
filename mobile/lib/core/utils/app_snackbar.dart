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
  if (s.contains('garment_contains_face') ||
      s.contains('衣服图检测到人像') ||
      s.contains('无模特') ||
      s.contains('白底商品图')) {
    return '衣服图里检测到人像，请改用无模特白底商品图';
  }
  if (s.contains('Garment cutout too small') ||
      s.contains('cutout too small')) {
    return '衣服主体过小或背景干扰过大，请换清晰近景商品图';
  }
  if (s.contains('Virtual try-on failed with status: 400')) {
    return '试衣请求被拒绝，请更换衣服图后重试';
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
