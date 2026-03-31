import 'package:flutter_test/flutter_test.dart';
import 'package:smart_outfit_assistant/main.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const ClothingAssistantApp());
    await tester.pump();
  });
}
