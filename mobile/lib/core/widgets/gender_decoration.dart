import 'package:flutter/material.dart';
import 'dart:math' as math;

/// Gender-based decoration widget using CustomPaint.
/// Male segment: Geometric bamboo pattern
/// Neutral segment: Chinese fret pattern
/// Female segment: Floral pattern
class GenderDecoration extends StatelessWidget {
  final double genderExpression;
  final double size;
  final double opacity;

  const GenderDecoration({
    super.key,
    required this.genderExpression,
    this.size = 200,
    this.opacity = 0.15,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _GenderDecorationPainter(
        genderExpression: genderExpression,
        opacity: opacity,
      ),
    );
  }
}

class _GenderDecorationPainter extends CustomPainter {
  final double genderExpression;
  final double opacity;

  _GenderDecorationPainter({
    required this.genderExpression,
    required this.opacity,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;

    if (genderExpression < 0.3) {
      _paintBambooPattern(canvas, center, radius);
    } else if (genderExpression < 0.7) {
      _paintFretPattern(canvas, center, radius);
    } else {
      _paintFloralPattern(canvas, center, radius);
    }
  }

  void _paintBambooPattern(Canvas canvas, Offset center, double radius) {
    final paint = Paint()
      ..color = const Color(0xFF2D5A47).withOpacity(opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    // Vertical lines (bamboo stalks)
    for (var i = 0; i < 5; i++) {
      final x = center.dx - radius + (radius * 2 / 5) * i + radius / 5;
      canvas.drawLine(
        Offset(x, center.dy - radius),
        Offset(x, center.dy + radius),
        paint,
      );
    }

    // Horizontal segments
    for (var y = center.dy - radius; y < center.dy + radius; y += radius / 3) {
      canvas.drawLine(
        Offset(center.dx - radius, y),
        Offset(center.dx + radius, y),
        paint,
      );
    }
  }

  void _paintFretPattern(Canvas canvas, Offset center, double radius) {
    final paint = Paint()
      ..color = const Color(0xFF8B7355).withOpacity(opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    // Concentric circles
    for (var i = 1; i <= 4; i++) {
      canvas.drawCircle(center, radius * i / 4, paint);
    }

    // Radial lines
    for (var angle = 0.0; angle < 360; angle += 30) {
      final rad = angle * math.pi / 180;
      final x = center.dx + radius * math.cos(rad);
      final y = center.dy + radius * math.sin(rad);
      canvas.drawLine(center, Offset(x, y), paint);
    }
  }

  void _paintFloralPattern(Canvas canvas, Offset center, double radius) {
    final paint = Paint()
      ..color = const Color(0xFFD4A5A5).withOpacity(opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    // Draw petals
    for (var i = 0; i < 8; i++) {
      final angle = i * math.pi / 4;
      final petalCenter = Offset(
        center.dx + radius * 0.4 * math.cos(angle),
        center.dy + radius * 0.4 * math.sin(angle),
      );

      final petalPath = Path();
      petalPath.addOval(Rect.fromCenter(
        center: petalCenter,
        width: radius * 0.4,
        height: radius * 0.25,
      ));

      canvas.drawPath(petalPath, paint);
    }

    // Center circle
    canvas.drawCircle(center, radius * 0.15, paint..style = PaintingStyle.fill);
    paint.style = PaintingStyle.stroke;
  }

  @override
  bool shouldRepaint(covariant _GenderDecorationPainter oldDelegate) {
    return oldDelegate.genderExpression != genderExpression ||
        oldDelegate.opacity != opacity;
  }
}
