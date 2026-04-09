import 'package:flutter_test/flutter_test.dart';
import 'package:smart_outfit_assistant/core/services/api_base_resolver.dart';
import 'package:smart_outfit_assistant/core/services/api_client.dart';
import 'package:smart_outfit_assistant/core/services/api_port_config.dart';

/// P1：锁定 API 基址与 /api/v1 后缀，避免回归。
void main() {
  test('kApiPort matches int.fromEnvironment default', () {
    const expected = int.fromEnvironment('API_PORT', defaultValue: 8010);
    expect(kApiPort, expected);
  });

  test('ApiClient default baseUrl is loopback with /api/v1', () {
    final c = ApiClient();
    expect(
      c.baseUrl,
      matches(RegExp(r'^http://127\.0\.0\.1:\d+/api/v1$')),
    );
  });

  test('resolveApiBaseUrl on VM/io matches kApiPort', () {
    final url = resolveApiBaseUrl();
    expect(url, 'http://127.0.0.1:$kApiPort/api/v1');
  });

  test('kPredictApiPort matches int.fromEnvironment default', () {
    const expected =
        int.fromEnvironment('PREDICT_API_PORT', defaultValue: 8010);
    expect(kPredictApiPort, expected);
  });

  test('resolvePredictApiBaseUrl on VM/io matches kPredictApiPort', () {
    final url = resolvePredictApiBaseUrl();
    expect(url, 'http://127.0.0.1:$kPredictApiPort');
  });
}
