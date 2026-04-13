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

  test('unwrapApiResponseEnvelope returns data from success envelope', () {
    final decoded = unwrapApiResponseEnvelope({
      'success': true,
      'data': {
        'image_url': '/uploads/u1/a.jpg',
      },
      'error': null,
    });

    expect(decoded, isA<Map>());
    expect(
      (decoded as Map)['image_url'],
      '/uploads/u1/a.jpg',
    );
  });

  test('unwrapApiResponseEnvelope preserves mapped error payloads', () {
    final decoded = unwrapApiResponseEnvelope({
      'success': false,
      'data': null,
      'error': {
        'message': 'missing image_url',
      },
    });

    expect(decoded, isA<Map>());
    expect((decoded as Map)['error'], 'missing image_url');
  });

  test('parseFastApiErrorBody extracts detail from FastAPI JSON', () {
    final msg = parseFastApiErrorBody('{"detail":"missing image_url"}');
    expect(msg, 'missing image_url');
  });

  test('unwrapApiResponseEnvelope unwraps POST /predict success payload', () {
    final inner = unwrapApiResponseEnvelope({
      'success': true,
      'data': {
        'score': 8.0,
        'recommendations': <dynamic>[],
        'explanation': 'ok',
      },
      'error': null,
    });
    expect(inner, isA<Map>());
    expect((inner as Map)['score'], 8.0);
    expect((inner as Map)['explanation'], 'ok');
  });
}
