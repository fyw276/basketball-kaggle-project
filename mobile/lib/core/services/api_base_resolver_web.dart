/// Flutter Web：API 与当前页使用**相同 loopback 主机名**（端口固定 8000），局域网用页面 host。
///
/// 若页面用 `localhost`、API 却用 `127.0.0.1`，Chrome 会按「私有网络访问」对 POST 预检更严，
/// 智能穿搭等 POST 可能失败，而 GET 天气仍可能成功；衣橱图片若已对齐为同源 origin 则正常。
/// 本机 loopback 时与地址栏一致（localhost / 127.0.0.1 / ::1），避免上述混用。
String resolveApiBaseUrl() {
  const apiPort = 8000;
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
    final scheme =
        (b.scheme == 'http' || b.scheme == 'https') ? b.scheme : 'http';
    return Uri(scheme: scheme, host: h, port: apiPort, path: '/api/v1')
        .toString();
  }
  final scheme =
      (b.scheme == 'http' || b.scheme == 'https') ? b.scheme : 'http';
  return Uri(
    scheme: scheme,
    host: h,
    port: apiPort,
    path: '/api/v1',
  ).toString();
}
