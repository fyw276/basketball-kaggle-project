import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// Web / desktop: include mouse / trackpad for [PageView] drag.
class SmartOutfitMouseDragScrollBehavior extends MaterialScrollBehavior {
  const SmartOutfitMouseDragScrollBehavior();

  @override
  Set<PointerDeviceKind> get dragDevices => {
        PointerDeviceKind.touch,
        PointerDeviceKind.mouse,
        PointerDeviceKind.trackpad,
        PointerDeviceKind.stylus,
      };
}

class SmartOutfitHintChip extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;

  const SmartOutfitHintChip({
    super.key,
    required this.icon,
    required this.text,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: color.withValues(alpha: 0.95),
            ),
          ),
        ],
      ),
    );
  }
}

class SmartOutfitStructuredAddressView extends StatelessWidget {
  final dynamic palette;
  final Map<String, String> addressParts;
  final String fallbackText;

  const SmartOutfitStructuredAddressView({
    super.key,
    required this.palette,
    required this.addressParts,
    required this.fallbackText,
  });

  @override
  Widget build(BuildContext context) {
    final chips = <Widget>[];
    void addChip(String label, String key, Color color) {
      final value = addressParts[key]?.trim() ?? '';
      if (value.isEmpty) return;
      chips.add(_AddressChip(label: label, value: value, color: color));
    }

    addChip('省', 'province', Colors.blue);
    addChip('市', 'city', Colors.green);
    addChip('区', 'district', Colors.orange);
    addChip('街道', 'street', Colors.purple);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: palette.divider.withValues(alpha: 0.9)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '地址信息',
            style: TextStyle(
              color: palette.textTitle,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          if (chips.isEmpty)
            Text(
              fallbackText,
              style: TextStyle(
                color: palette.textBody,
                fontSize: 11,
              ),
            )
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: chips,
            ),
        ],
      ),
    );
  }
}

class _AddressChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _AddressChip({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color.withValues(alpha: 0.95),
        ),
      ),
    );
  }
}

class SmartOutfitSummaryCard extends StatelessWidget {
  final dynamic palette;
  final bool hasImage;
  final bool weatherLoading;
  final bool weatherFallback;
  final Map<String, String> addressParts;
  final String moodText;
  final bool hasResult;

  const SmartOutfitSummaryCard({
    super.key,
    required this.palette,
    required this.hasImage,
    required this.weatherLoading,
    required this.weatherFallback,
    required this.addressParts,
    required this.moodText,
    required this.hasResult,
  });

  @override
  Widget build(BuildContext context) {
    final weatherStatus = weatherLoading
        ? '天气加载中'
        : weatherFallback
            ? '默认天气参数'
            : '定位天气就绪';
    final moodStatus = moodText.isEmpty ? '未填写（可选）' : '已填写';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: palette.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: palette.primary.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '生成前状态',
            style: TextStyle(
              color: palette.textTitle,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '参考图：${hasImage ? '已上传' : '未上传'}  |  天气：$weatherStatus  |  心情：$moodStatus',
            style: TextStyle(
              color: palette.textBody,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 8),
          SmartOutfitStructuredAddressView(
            palette: palette,
            addressParts: addressParts,
            fallbackText: weatherLoading
                ? '正在解析地址…'
                : weatherFallback
                    ? '未获取到详细地址'
                    : '地址已就绪',
          ),
          if (hasResult) ...[
            const SizedBox(height: 6),
            Text(
              '已生成结果，可点击“重新生成”获取另一组方案。',
              style: TextStyle(
                color: palette.textBody,
                fontSize: 11,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
