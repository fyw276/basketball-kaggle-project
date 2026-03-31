import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../theme/style_tokens.dart';

class ThemedBackground extends StatelessWidget {
  final StyleTokens tokens;
  final Widget child;

  const ThemedBackground(
      {super.key, required this.tokens, required this.child});

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(gradient: tokens.pageGradient()),
      child: CustomPaint(
        painter: _ArtPainter(tokens),
        child: child,
      ),
    );
  }
}

class _ArtPainter extends CustomPainter {
  final StyleTokens t;
  _ArtPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    switch (t.art) {
      case BackgroundArtKind.forest:
        _paintFlowerShop(canvas, size);
        break;
      case BackgroundArtKind.neo:
        _paintSportCampus(canvas, size);
        break;
      case BackgroundArtKind.minimal:
        // 苹果极简：完全无装饰
        break;
    }
  }

  void _paintFlowerShop(Canvas canvas, Size s) {
    final vine = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.1
      ..color = t.accent.withOpacity(0.14)
      ..strokeCap = StrokeCap.round;
    final flower = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = t.primary.withOpacity(0.16)
      ..strokeCap = StrokeCap.round;
    final dot = Paint()..color = const Color(0xFFFFF0F4).withOpacity(0.65);

    // vines
    for (var i = 0; i < 5; i++) {
      final y = (s.height * (0.18 + i * 0.16)) % s.height;
      final path = Path()
        ..moveTo(-30, y)
        ..cubicTo(s.width * 0.22, y - 18, s.width * 0.52, y + 28,
            s.width * 0.80, y - 10)
        ..cubicTo(s.width * 0.92, y - 24, s.width * 1.12, y + 26, s.width + 40,
            y + 4);
      canvas.drawPath(path, vine);
    }

    // small daisies / baby's breath clusters
    void daisy(Offset c, double r) {
      for (var k = 0; k < 6; k++) {
        final a = (math.pi * 2 / 6) * k;
        final p = Offset(math.cos(a) * r * 0.55, math.sin(a) * r * 0.55);
        canvas.drawCircle(c + p, r * 0.32, flower);
      }
      canvas.drawCircle(c, r * 0.22, dot);
    }

    final rnd = math.Random(2026);
    for (var i = 0; i < 28; i++) {
      final x = rnd.nextDouble() * s.width;
      final y = rnd.nextDouble() * s.height;
      final r = 6 + rnd.nextDouble() * 10;
      if ((x < s.width * 0.2 && y < s.height * 0.35) ||
          (x > s.width * 0.75 && y > s.height * 0.60)) {
        daisy(Offset(x, y), r);
      }
    }

    // leaf silhouettes
    final leaf = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0
      ..color = t.accent.withOpacity(0.10);
    for (var i = 0; i < 10; i++) {
      final x = (s.width * 0.08) + i * 48.0;
      final y = (s.height * 0.82) + (i % 2) * 10.0;
      final path = Path()
        ..moveTo(x, y)
        ..quadraticBezierTo(x + 18, y - 18, x + 28, y - 2)
        ..quadraticBezierTo(x + 16, y + 16, x, y);
      canvas.drawPath(path, leaf);
    }
  }

  void _paintSportCampus(Canvas canvas, Size s) {
    // track lanes (light grey)
    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..color = const Color(0xFFCBD5E1).withOpacity(0.35);
    for (var i = 0; i < 6; i++) {
      final y = s.height * (0.18 + i * 0.12);
      final path = Path()
        ..moveTo(-40, y)
        ..quadraticBezierTo(s.width * 0.45, y - 18, s.width + 40, y + 12);
      canvas.drawPath(path, track);
    }

    // subtle grid
    final grid = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = const Color(0xFF94A3B8).withOpacity(0.18);
    const step = 56.0;
    for (double x = 0; x < s.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, s.height), grid);
    }
    for (double y = 0; y < s.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(s.width, y), grid);
    }

    // sun bokeh spots
    final sun = Paint()..color = const Color(0xFFFFF6D8).withOpacity(0.35);
    canvas.drawCircle(Offset(s.width * 0.82, s.height * 0.18), 90, sun);
    canvas.drawCircle(Offset(s.width * 0.72, s.height * 0.26), 54,
        sun..color = sun.color.withOpacity(0.22));
    canvas.drawCircle(Offset(s.width * 0.90, s.height * 0.30), 38,
        sun..color = sun.color.withOpacity(0.18));

    // small corner triangles
    final tri = Paint()..color = t.primary.withOpacity(0.10);
    final p = Path()
      ..moveTo(s.width * 0.10, s.height * 0.82)
      ..lineTo(s.width * 0.18, s.height * 0.82)
      ..lineTo(s.width * 0.18, s.height * 0.74)
      ..close();
    canvas.drawPath(p, tri);
  }

  @override
  bool shouldRepaint(covariant _ArtPainter oldDelegate) {
    return oldDelegate.t.art != t.art ||
        oldDelegate.t.primary != t.primary ||
        oldDelegate.t.accent != t.accent ||
        oldDelegate.t.bg1 != t.bg1 ||
        oldDelegate.t.bg2 != t.bg2;
  }
}
