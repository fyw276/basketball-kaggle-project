/// Web platform: resolve API base URL from browser hostname.
/// Import this conditionally via api_base_resolver.dart on web platform.
import 'package:flutter/foundation.dart';

String resolveApiBaseUrl() {
  if (!kIsWeb) {
    return 'http://127.0.0.1:8000/api/v1';
  }

  // On web, resolve from current browser hostname
  // This avoids CORS / localhost vs 127.0.0.1 mismatch issues
  // In Flutter web, we can't directly access window.location,
  // so we default to localhost mapping
  return 'http://localhost:8000/api/v1';
}
