/// 将后端返回的相对路径转为可加载的绝对 URL。
String? resolveGarmentImageUrl(String? raw, String apiBaseUrl) {
  if (raw == null || raw.isEmpty) return null;
  final t = raw.trim();
  if (t.startsWith('http://') || t.startsWith('https://')) return t;
  if (t.startsWith('data:')) return t;
  final origin = apiBaseUrl.replaceAll(RegExp(r'/api/v1/?$'), '');
  // 服务器上的绝对路径里常含 `/uploads/...`（历史数据只有 image_path 时）
  final norm = t.replaceAll('\\', '/');
  final lower = norm.toLowerCase();
  final uidx = lower.indexOf('/uploads/');
  if (uidx >= 0) {
    return '$origin${norm.substring(uidx)}';
  }
  if (t.startsWith('/')) return '$origin$t';
  return '$origin/$t';
}
