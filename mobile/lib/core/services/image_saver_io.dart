import 'dart:io' as io;
import 'dart:typed_data';

import 'package:gal/gal.dart';
import 'package:path_provider/path_provider.dart';

/// 将图片字节数据保存到设备相册（非 Web 移动端）。
Future<void> saveImageToGallery(Uint8List bytes, {String? album}) async {
  final tmpDir = await getTemporaryDirectory();
  final tmpFile = io.File(
    '${tmpDir.path}/tryon_${DateTime.now().millisecondsSinceEpoch}.jpg',
  );
  await tmpFile.writeAsBytes(bytes);
  await Gal.putImage(tmpFile.path, album: album ?? '智能穿搭助手');
}
