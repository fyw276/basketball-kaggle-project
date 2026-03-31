/// Native platform (iOS/Android/Desktop): use fixed local address.
/// Import this conditionally via api_base_resolver.dart on native platform.
String resolveApiBaseUrl() {
  // Android emulator can reach host via 10.0.2.2
  // iOS simulator uses localhost
  // Desktop uses 127.0.0.1
  return 'http://127.0.0.1:8000/api/v1';
}
