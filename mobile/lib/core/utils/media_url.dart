/// 将后端返回的相对路径或历史混用 host 的绝对 URL 转为当前 API 同源、可加载的地址。
String? resolveGarmentImageUrl(String? raw, String apiBaseUrl) {
  if (raw == null || raw.isEmpty) return null;
  final t = raw.trim();
  if (t.startsWith('data:')) return t;

  final origin = apiBaseUrl.replaceAll(RegExp(r'/api/v1/?$'), '');

  if (t.startsWith('http://') || t.startsWith('https://')) {
    return _normalizeAbsoluteToApiOrigin(t, origin);
  }

  final norm = t.replaceAll('\\', '/');
  final lower = norm.toLowerCase();
  final uidx = lower.indexOf('/uploads/');
  if (uidx >= 0) {
    return '$origin${norm.substring(uidx)}';
  }
  if (lower.startsWith('uploads/')) {
    return '$origin/$norm';
  }
  if (t.startsWith('/')) return '$origin$t';
  return '$origin/$t';
}

/// 将 `http://127.0.0.1:8010/...` 与 `http://127.0.0.1:8010/...` 等与 [apiOrigin] 对齐，避免 Web 跨 host 导致图片/请求失败。
String _normalizeAbsoluteToApiOrigin(String url, String apiOrigin) {
  try {
    final o = Uri.parse(apiOrigin);
    final u = Uri.parse(url);
    final pathLower = u.path.toLowerCase();
    if (!pathLower.contains('/uploads/')) return url;
    return '${o.scheme}://${o.host}${o.hasPort ? ':${o.port}' : ''}'
        '${u.path}${u.hasQuery ? '?${u.query}' : ''}';
  } catch (_) {
    return url;
  }
}
