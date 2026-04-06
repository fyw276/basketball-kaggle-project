import 'dart:io' show Platform;

import 'api_port_config.dart';

/// 非 Web：默认本机后端。Android 模拟器访问宿主机用 10.0.2.2；真机请 adb reverse 或改局域网 IP。
String resolveApiBaseUrl() {
  try {
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:$kApiPort/api/v1';
    }
  } catch (_) {}
  return 'http://127.0.0.1:$kApiPort/api/v1';
}

/// AI 穿搭风格分服务基址（`POST /predict`）。Android 模拟器用 10.0.2.2 访问宿主机。
String resolvePredictApiBaseUrl() {
  try {
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:$kPredictApiPort';
    }
  } catch (_) {}
  return kDefaultPredictApiBaseUrl;
}
