// 按平台解析后端 API Base（`/api/v1` 前缀已含）与 AI predict 基址（8765）。
export 'api_base_resolver_io.dart'
    if (dart.library.html) 'api_base_resolver_web.dart';
