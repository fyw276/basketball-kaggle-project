import 'package:flutter/material.dart';
import 'dart:math' as math;

import '../theme/fashion_palettes.dart';

/// 性别表达区间装饰：偏男竹叶 / 中性回纹 / 偏女小碎花（配色随全局 Palette 色系）
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

    if (genderExpression <= FashionPalettes.maleThreshold) {
      _paintBambooPattern(canvas, center, radius);
    } else if (genderExpression < FashionPalettes.femaleThreshold) {
      _paintFretPattern(canvas, center, radius);
    } else {
      _paintFloralPattern(canvas, center, radius);
    }
  }

  void _paintBambooPattern(Canvas canvas, Offset center, double radius) {
    final c = FashionPalettes.fromGenderExpression(0.15).primary;
    final paint = Paint()
      ..color = c.withValues(alpha: opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    // 竹节与细叶示意
    for (var i = 0; i < 4; i++) {
      final x = center.dx - radius * 0.7 + (radius * 1.4 / 3) * i;
      canvas.drawLine(
        Offset(x, center.dy - radius * 0.85),
        Offset(x, center.dy + radius * 0.85),
        paint,
      );
      for (var j = -1; j <= 1; j++) {
        final y = center.dy + j * radius * 0.35;
        final leaf = Path()
          ..moveTo(x, y)
          ..quadraticBezierTo(x + radius * 0.22, y - radius * 0.08,
              x + radius * 0.35, y + radius * 0.05);
        canvas.drawPath(leaf, paint..strokeWidth = 1.2);
      }
    }
    paint.strokeWidth = 1.5;
  }

  void _paintFretPattern(Canvas canvas, Offset center, double radius) {
    final c = FashionPalettes.fromGenderExpression(0.5).primary;
    final paint = Paint()
      ..color = c.withValues(alpha: opacity)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    // 简化回纹：方折路径环绕
    final u = radius * 0.2;
    void drawKey(Offset o) {
      final p = Path()
        ..moveTo(o.dx, o.dy)
        ..relativeLineTo(u, 0)
        ..relativeLineTo(0, u)
        ..relativeLineTo(-u, 0)
        ..relativeLineTo(0, -u * 0.5)
        ..relativeLineTo(-u * 0.5, 0)
        ..relativeLineTo(0, u * 0.5);
      canvas.drawPath(p, paint);
    }

    for (var row = -2; row <= 2; row++) {
      for (var col = -2; col <= 2; col++) {
        drawKey(Offset(
          center.dx + col * u * 2.2,
          center.dy + row * u * 2.2,
        ));
      }
    }
  }

  void _paintFloralPattern(Canvas canvas, Offset center, double radius) {
    final c = FashionPalettes.fromGenderExpression(0.85).primary;
    final paint = Paint()
      ..color = c.withValues(alpha: opacity)
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
