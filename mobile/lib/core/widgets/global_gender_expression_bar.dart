import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../theme/fashion_palettes.dart';
import '../providers/theme_provider.dart';

/// 全局性别表达指数滑块栏（底部分析页使用）。
/// 标签：0 = 偏男性化穿搭，1 = 偏女性化穿搭。
class GlobalGenderExpressionBar extends StatelessWidget {
  final double? value;
  final ValueChanged<double>? onChanged;
  final bool showLabel;

  const GlobalGenderExpressionBar({
    super.key,
    this.value,
    this.onChanged,
    this.showLabel = true,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, _) {
        final currentValue = value ?? themeProvider.genderExpression;
        final gradient = FashionPalettes.genderBarGradient;

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 8,
                offset: const Offset(0, -2),
              ),
            ],
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (showLabel)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          '性别表达指数',
                          style:
                              Theme.of(context).textTheme.bodySmall?.copyWith(
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onSurfaceVariant,
                                  ),
                        ),
                        Text(
                          FashionPalettes.genderLabel(currentValue),
                          style: Theme.of(context)
                              .textTheme
                              .bodySmall
                              ?.copyWith(
                                color: Theme.of(context).colorScheme.primary,
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                      ],
                    ),
                  ),
                SliderTheme(
                  data: SliderThemeData(
                    trackHeight: 6,
                    thumbShape:
                        const RoundSliderThumbShape(enabledThumbRadius: 12),
                    overlayShape:
                        const RoundSliderOverlayShape(overlayRadius: 20),
                    activeTrackColor: _getThumbColor(currentValue),
                    inactiveTrackColor: gradient[0].withValues(alpha: 0.2),
                    thumbColor: _getThumbColor(currentValue),
                    overlayColor:
                        _getThumbColor(currentValue).withValues(alpha: 0.2),
                  ),
                  child: Slider(
                    value: currentValue,
                    onChanged: onChanged ?? themeProvider.setGenderExpression,
                    min: 0.0,
                    max: 1.0,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '偏男性化',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: gradient[0],
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                      Text(
                        '中性',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: gradient[1],
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                      Text(
                        '偏女性化',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: gradient[2],
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Color _getThumbColor(double value) {
    final gradient = FashionPalettes.genderBarGradient;
    if (value <= 0.3) {
      return gradient[0];
    } else if (value < 0.7) {
      return gradient[1];
    } else {
      return gradient[2];
    }
  }
}
