/// Conditional import stub for API base URL resolver.
/// On web: uses api_base_resolver_web.dart
/// On native: uses api_base_resolver_io.dart
String resolveApiBaseUrl() {
  // This file is a stub - actual implementation uses conditional imports
  // via build runner or platform-specific files
  return 'http://localhost:8000/api/v1';
}
