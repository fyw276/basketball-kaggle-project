import 'api_port_config.dart';

/// Flutter Web API 基址。
///
/// **本机环回一律用 IPv4 `127.0.0.1`**，不用浏览器地址栏里的 `localhost` / `::1`。
/// 否则在 Windows 上易出现「`localhost` 解析到 ::1、与仅监听 IPv4 的进程不一致」或
/// 「同端口存在多个监听时连错进程」，表现为登录 **404**、根路径非本仓库 JSON。
///
/// 局域网调试仍用当前页 host；端口见 [kApiPort]（默认与后端 [.env] PORT 一致）。
String resolveApiBaseUrl() {
  const apiPort = kApiPort;
  final b = Uri.base;
  final h = b.host;
  if (h.isEmpty) {
    return 'http://127.0.0.1:$apiPort/api/v1';
  }
  final isLoopback = h == 'localhost' ||
      h == '127.0.0.1' ||
      h == '::1' ||
      h.startsWith('127.');
  if (!isLoopback) {
    // 线上优先走同源反向代理（/api/v1），避免浏览器直连 :8010 被防火墙拦截。
    return '${b.origin}/api/v1';
  }
  return 'http://127.0.0.1:$apiPort/api/v1';
}

/// AI 穿搭风格分（`POST /predict`），默认与主 API 同端口（8010）。
String resolvePredictApiBaseUrl() {
  const predictPort = kPredictApiPort;
  final b = Uri.base;
  final h = b.host;
  if (h.isEmpty) {
    return 'http://127.0.0.1:$predictPort';
  }
  final isLoopback = h == 'localhost' ||
      h == '127.0.0.1' ||
      h == '::1' ||
      h.startsWith('127.');
  if (!isLoopback) {
    // 与主 API 一致，线上走同源 /predict（由 Nginx 转发到后端）。
    return b.origin;
  }
  return 'http://127.0.0.1:$predictPort';
}
