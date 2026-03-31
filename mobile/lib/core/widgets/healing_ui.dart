import 'package:flutter/material.dart';

class HealingPalette {
  static const Color creamGreen = Color(0xFFDCEBD7);
  static const Color creamApricot = Color(0xFFF6E6D3);
  static const Color softPink = Color(0xFFF8DCE5);
  static const Color lightBlue = Color(0xFFDBEAF7);
  static const Color mintDeep = Color(0xFF92C790);
  static const Color textMain = Color(0xFF5B5B5B);
  static const Color textSoft = Color(0xFF7C7C7C);
}

class HealingScaffold extends StatelessWidget {
  final String title;
  final Widget child;
  final bool showBack;

  const HealingScaffold({
    super.key,
    required this.title,
    required this.child,
    this.showBack = true,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFFFFCF7), Color(0xFFEEF7EC), Color(0xFFF7FAFF)],
          ),
        ),
        child: SafeArea(
          child: Stack(
            children: [
              const Positioned(
                  left: 12,
                  top: 80,
                  child: Text('☁', style: TextStyle(fontSize: 28))),
              const Positioned(
                  right: 14,
                  top: 130,
                  child: Text('🌼', style: TextStyle(fontSize: 22))),
              const Positioned(
                  left: 18,
                  bottom: 30,
                  child: Text('🍄', style: TextStyle(fontSize: 20))),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF8EF),
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: const Color(0xFFF0E6D7)),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x1F7A8C7A),
                            blurRadius: 16,
                            offset: Offset(0, 6),
                          ),
                        ],
                      ),
                      child: Row(
                        children: [
                          if (showBack)
                            InkWell(
                              borderRadius: BorderRadius.circular(12),
                              onTap: () => Navigator.of(context).maybePop(),
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: const Color(0xFFF0F9EB),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: const Icon(Icons.arrow_back_rounded,
                                    color: Color(0xFF5E7D5F)),
                              ),
                            )
                          else
                            const SizedBox(width: 34, height: 34),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              title,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF6A876B),
                              ),
                            ),
                          ),
                          const SizedBox(width: 34, height: 34),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    Expanded(child: child),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class HealingCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;

  const HealingCard({super.key, required this.child, this.padding});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding ?? const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFEEF8E8), Color(0xFFFFF5E8)],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE5EFDD)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x1F7A8C7A),
            blurRadius: 14,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

class HealingDashedUpload extends StatelessWidget {
  final VoidCallback onTap;
  final String label;

  const HealingDashedUpload({
    super.key,
    required this.onTap,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFFBFFF8),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFBCDAB4), width: 2),
        ),
        child: Column(
          children: [
            const Text('👗🐰', style: TextStyle(fontSize: 30)),
            const SizedBox(height: 6),
            Text(label,
                style: const TextStyle(
                    color: HealingPalette.textSoft, fontSize: 14)),
            const SizedBox(height: 2),
            const Text('支持 JPG / PNG',
                style: TextStyle(color: HealingPalette.textSoft, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class HealingLoading extends StatelessWidget {
  final bool loading;
  final String text;

  const HealingLoading({
    super.key,
    required this.loading,
    required this.text,
  });

  @override
  Widget build(BuildContext context) {
    if (!loading) return const SizedBox.shrink();
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const _LeafSpinner(),
        const SizedBox(width: 8),
        Text(text,
            style: const TextStyle(
                color: Color(0xFF6F866F), fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _LeafSpinner extends StatefulWidget {
  const _LeafSpinner();

  @override
  State<_LeafSpinner> createState() => _LeafSpinnerState();
}

class _LeafSpinnerState extends State<_LeafSpinner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RotationTransition(
      turns: _controller,
      child: const SizedBox(
        width: 26,
        height: 26,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Center(child: Text('🍃', style: TextStyle(fontSize: 20))),
            Positioned(
                right: -4,
                bottom: -4,
                child: Text('🦆', style: TextStyle(fontSize: 12))),
          ],
        ),
      ),
    );
  }
}
