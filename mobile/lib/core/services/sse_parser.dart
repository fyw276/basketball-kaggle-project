import 'dart:convert';

/// A single parsed SSE message.
class SseMessage {
  /// The `event:` field value (empty string if not present).
  final String type;

  /// The `data:` field value (may be concatenated from multiple `data:` lines).
  final String data;

  const SseMessage({required this.type, required this.data});

  @override
  String toString() =>
      'SseMessage(type: $type, data: ${data.length > 80 ? '${data.substring(0, 80)}...' : data})';
}

/// Proper SSE parser that handles cross-chunk line boundaries.
///
/// The HTTP stream may split a single SSE message across multiple chunks.
/// This parser buffers incomplete lines and reassembles them before parsing.
Stream<SseMessage> parseSseStream(Stream<List<int>> byteStream) async* {
  String buffer = '';
  String currentEvent = '';
  final dataLines = <String>[];

  await for (final bytes in byteStream.transform(utf8.decoder)) {
    buffer += bytes;
    final lines = buffer.split('\n');
    buffer = lines.removeLast(); // keep incomplete trailing line in buffer

    for (final line in lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.add(line.substring(5).trim());
      } else if (line.trim().isEmpty) {
        // Blank line = end of SSE message
        if (dataLines.isNotEmpty) {
          final data = dataLines.join('\n');
          yield SseMessage(type: currentEvent, data: data);
          currentEvent = '';
          dataLines.clear();
        }
      }
    }
  }

  // Flush any remaining buffered data
  if (dataLines.isNotEmpty) {
    yield SseMessage(
      type: currentEvent,
      data: dataLines.join('\n'),
    );
  }
}
