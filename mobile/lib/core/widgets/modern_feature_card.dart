import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/theme_provider.dart';
import '../theme/style_tokens.dart';
import '../theme/theme_model.dart';

class ModernFeatureCard extends StatefulWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final LinearGradient gradient;
  final VoidCallback onTap;
  final String? emoji;

  const ModernFeatureCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.gradient,
    required this.onTap,
    this.emoji,
  });

  @override
  State<ModernFeatureCard> createState() => _ModernFeatureCardState();
}

class _ModernFeatureCardState extends State<ModernFeatureCard> {
  bool _hovered = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final style = context.watch<ThemeProvider>().style;
    final tokens = StyleTokens.fromStyle(style);

    final radius = tokens.cardRadius;
    final scale = style == UserGender.female ? (_hovered ? 1.03 : 1.0) : 1.0;
    final dy = style == UserGender.male ? (_pressed ? 1.0 : 0.0) : 0.0;
    final opacity = style == UserGender.none ? (_pressed ? 0.92 : 1.0) : 1.0;
    final animDuration = style == UserGender.female
        ? const Duration(milliseconds: 300)
        : style == UserGender.male
            ? const Duration(milliseconds: 200)
            : const Duration(milliseconds: 160);

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTapDown: (_) => setState(() => _pressed = true),
        onTapUp: (_) => setState(() => _pressed = false),
        onTapCancel: () => setState(() => _pressed = false),
        onTap: widget.onTap,
        child: AnimatedScale(
          duration: animDuration,
          curve: Curves.easeOutCubic,
          scale: scale,
          child: AnimatedOpacity(
            duration: animDuration,
            curve: Curves.easeOutCubic,
            opacity: opacity,
            child: AnimatedContainer(
              duration: animDuration,
              curve: Curves.easeOutCubic,
              transform: Matrix4.translationValues(0, dy, 0),
              decoration: BoxDecoration(
                gradient: widget.gradient,
                borderRadius: BorderRadius.circular(radius),
                boxShadow: tokens.cardShadow(),
                border: Border.all(
                  color: style == UserGender.female
                      ? tokens.border.withOpacity(0.75)
                      : style == UserGender.male
                          ? tokens.border.withOpacity(0.90)
                          : tokens.border.withOpacity(0.70),
                ),
              ),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: widget.onTap,
                  borderRadius: BorderRadius.circular(radius),
                  child: Stack(
                    children: [
                      if (style == UserGender.female)
                        const Positioned(
                            right: 10, top: 10, child: _FlowerSticker())
                      else if (style == UserGender.male)
                        const Positioned(
                            right: 10, top: 10, child: _SportCornerMark()),
                      Padding(
                        padding: EdgeInsets.all(
                            style == UserGender.male ? 16.0 : 20.0),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            if (style == UserGender.female)
                              const Padding(
                                padding: EdgeInsets.only(bottom: 8),
                                child:
                                    Text('🐰', style: TextStyle(fontSize: 22)),
                              ),
                            if (widget.emoji != null) ...[
                              Text(widget.emoji!,
                                  style: const TextStyle(fontSize: 48)),
                              const SizedBox(height: 8),
                            ],
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(
                                    style == UserGender.male ? 0.18 : 0.22),
                                borderRadius: BorderRadius.circular(
                                    style == UserGender.male ? 8 : 16),
                              ),
                              child: Icon(widget.icon,
                                  size: 36, color: Colors.white),
                            ),
                            const SizedBox(height: 14),
                            Text(
                              widget.title,
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: style == UserGender.male
                                    ? FontWeight.w800
                                    : FontWeight.w700,
                                color: Colors.white,
                                letterSpacing:
                                    style == UserGender.male ? 0.6 : 0.25,
                              ),
                              textAlign: TextAlign.center,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              widget.subtitle,
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.white.withOpacity(0.86),
                                fontWeight: FontWeight.w600,
                              ),
                              textAlign: TextAlign.center,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _FlowerSticker extends StatelessWidget {
  const _FlowerSticker();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: const Size(34, 34),
      painter: _FlowerStickerPainter(),
    );
  }
}

class _FlowerStickerPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final petal = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = Colors.white.withOpacity(0.60)
      ..strokeCap = StrokeCap.round;
    final center = Paint()..color = const Color(0xFFFFF0B8).withOpacity(0.75);
    final c = Offset(size.width * 0.62, size.height * 0.40);
    for (var i = 0; i < 6; i++) {
      final a = (math.pi * 2 / 6) * i;
      final p = c + Offset(math.cos(a) * 8, math.sin(a) * 8);
      canvas.drawCircle(p, 5.5, petal);
    }
    canvas.drawCircle(c, 3.6, center);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _SportCornerMark extends StatelessWidget {
  const _SportCornerMark();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: const Size(34, 34),
      painter: _SportMarkPainter(),
    );
  }
}

class _SportMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..color = Colors.white.withOpacity(0.60);
    final tri = Path()
      ..moveTo(size.width * 0.18, size.height * 0.18)
      ..lineTo(size.width * 0.62, size.height * 0.18)
      ..lineTo(size.width * 0.18, size.height * 0.62)
      ..close();
    canvas.drawPath(tri, p);
    canvas.drawLine(
      Offset(size.width * 0.20, size.height * 0.84),
      Offset(size.width * 0.86, size.height * 0.18),
      p..strokeWidth = 2.2,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
