/// 将后端返回的相对路径转为可加载的绝对 URL。
String? resolveGarmentImageUrl(String? raw, String apiBaseUrl) {
  if (raw == null || raw.isEmpty) return null;
  final t = raw.trim();
  if (t.startsWith('http://') || t.startsWith('https://')) return t;
  if (t.startsWith('data:')) return t;
  final origin = apiBaseUrl.replaceAll(RegExp(r'/api/v1/?$'), '');
  if (t.startsWith('/')) return '$origin$t';
  return '$origin/$t';
}
