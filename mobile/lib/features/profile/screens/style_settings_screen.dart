import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/theme_provider.dart';

/// 外观设置：仅深色模式等；性别表达指数在「设置」主页调整，已移除男/女风格选项。
class StyleSettingsScreen extends StatelessWidget {
  const StyleSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final tp = context.watch<ThemeProvider>();
    final p = tp.palette;

    return Scaffold(
      backgroundColor: p.background,
      appBar: AppBar(
        title: const Text('外观'),
        backgroundColor: p.background,
        foregroundColor: p.textTitle,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: p.surface,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: p.divider),
              boxShadow: p.cardShadows,
            ),
            child: SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('深色模式',
                  style: TextStyle(
                      color: p.textTitle, fontWeight: FontWeight.w600)),
              subtitle: Text(
                '与性别表达指数配色独立；指数请在「设置」页调整。',
                style: TextStyle(color: p.textBody, fontSize: 13),
              ),
              value: tp.themeMode == ThemeMode.dark,
              activeThumbColor: p.primary,
              onChanged: (v) {
                tp.setThemeMode(v ? ThemeMode.dark : ThemeMode.light);
              },
            ),
          ),
        ],
      ),
    );
  }
}
