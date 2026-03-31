import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/theme_model.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/widgets/themed_background.dart';

class StyleSettingsScreen extends StatelessWidget {
  const StyleSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();
    final current = themeProvider.style;
    final tokens = StyleTokens.fromStyle(current);
    final cs = Theme.of(context).colorScheme;

    Widget option(UserGender style, String title, String subtitle) {
      final selected = current == style;
      return InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () {
          themeProvider.setStyle(style);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              behavior: SnackBarBehavior.floating,
              elevation: 12,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14)),
              content: const Text('切换风格将立即应用到所有页面，下次打开仍生效'),
            ),
          );
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOutCubic,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: tokens.surface.withOpacity(selected ? 0.85 : 0.65),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: selected
                  ? tokens.primary.withOpacity(0.55)
                  : tokens.border.withOpacity(0.75),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: tokens.primary.withOpacity(selected ? 0.14 : 0.08),
                blurRadius: selected ? 24 : 16,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: selected ? tokens.primary : tokens.border,
                    width: 2,
                  ),
                ),
                child: Center(
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    width: selected ? 9 : 0,
                    height: selected ? 9 : 0,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: tokens.primary,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: GoogleFonts.inter(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w800,
                        color: cs.onSurface.withOpacity(0.92),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: GoogleFonts.inter(
                        fontSize: 12.5,
                        height: 1.35,
                        fontWeight: FontWeight.w600,
                        color: cs.onSurface.withOpacity(0.62),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
          title: Text('风格设置', style: tokens.titleStyle.copyWith(fontSize: 18))),
      body: ThemedBackground(
        tokens: tokens,
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: tokens.pageMaxWidth),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
                children: [
                  Text(
                    '切换风格将立即应用到所有页面，下次打开仍保留。',
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      height: 1.45,
                      color: tokens.muted.withOpacity(0.95),
                    ),
                  ),
                  const SizedBox(height: 14),
                  option(UserGender.none, '中性（默认）', '黑白灰 + 浅蓝点缀，极简干净'),
                  const SizedBox(height: 10),
                  option(UserGender.male, '男生', '冷调深色、几何线条、力量感与秩序'),
                  const SizedBox(height: 10),
                  option(UserGender.female, '女生', '浅绿米白、植物纹理、温柔治愈'),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
