import 'package:flutter/material.dart';
import 'dart:math' as math;

/// Chinese fret pattern decoration using CustomPaint.
/// Used as background decoration for gender-neutral segment.
class ChineseFretRing extends StatelessWidget {
  final double size;
  final Color color;
  final double strokeWidth;

  const ChineseFretRing({
    super.key,
    this.size = 120,
    this.color = const Color(0xFF8B7355),
    this.strokeWidth = 2,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _ChineseFretPainter(
        color: color,
        strokeWidth: strokeWidth,
      ),
    );
  }
}

class _ChineseFretPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;

  _ChineseFretPainter({
    required this.color,
    required this.strokeWidth,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withOpacity(0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - strokeWidth;

    // Draw outer circle
    canvas.drawCircle(center, radius, paint);

    // Draw inner circles forming fret pattern
    final innerCount = 3;
    for (var i = 0; i < innerCount; i++) {
      final innerRadius = radius * (0.6 - i * 0.15);
      canvas.drawCircle(center, innerRadius, paint);
    }

    // Draw connecting lines (fret pattern)
    for (var angle = 0.0; angle < 360; angle += 30) {
      final rad = angle * math.pi / 180;
      final startX = center.dx + radius * 0.15 * math.cos(rad);
      final startY = center.dy + radius * 0.15 * math.sin(rad);
      final endX = center.dx + radius * math.cos(rad);
      final endY = center.dy + radius * math.sin(rad);

      canvas.drawLine(
        Offset(startX, startY),
        Offset(endX, endY),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ChineseFretPainter oldDelegate) {
    return oldDelegate.color != color || oldDelegate.strokeWidth != strokeWidth;
  }
}
