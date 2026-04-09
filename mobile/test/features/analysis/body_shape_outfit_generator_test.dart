import 'package:flutter_test/flutter_test.dart';

import 'package:smart_outfit_assistant/features/analysis/services/body_shape_outfit_generator.dart';

void main() {
  test('generateBodyShapeOutfits returns 3 outfits with expected fields', () {
    final profile = <String, dynamic>{
      'height': 170,
      'body_type': '梨形',
      'style_preference': ['通勤', '简约'],
    };

    final outfits = generateBodyShapeOutfits(profile, seed: 42);
    expect(outfits.length, 3);
    for (final o in outfits) {
      expect(o['title'], isA<String>());
      expect((o['title'] as String).trim(), isNotEmpty);
      expect(o['items'], isA<List>());
      expect((o['items'] as List).isNotEmpty, true);
      expect(o['fit_explain'], isA<String>());
      expect((o['fit_explain'] as String).contains('体型：梨形'), true);
      expect((o['fit_explain'] as String).contains('风格：通勤'), true);
    }
  });
}
