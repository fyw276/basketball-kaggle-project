import 'dart:typed_data';

/// Web 端存根：下载图片在新标签页打开。
Future<void> saveImageToGallery(Uint8List bytes, {String? album}) async {
  // Web 端不需要保存到相册，直接下载文件即可。
  // 调用方应使用 url_launcher 打开 URL，而非调用此方法。
  // 本 stub 保留以保持 API 签名一致。
}
