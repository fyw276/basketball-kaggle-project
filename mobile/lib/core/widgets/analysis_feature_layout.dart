import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/theme_provider.dart';
import '../widgets/gender_decoration.dart';
import '../widgets/global_gender_expression_bar.dart';

/// Common layout scaffold for all analysis feature screens.
/// Provides: Scaffold + GenderDecorationBackground + GlobalGenderExpressionBar
class AnalysisFeatureLayout extends StatelessWidget {
  final String title;
  final Widget body;
  final Widget? floatingActionButton;
  final List<Widget>? actions;
  final bool showGenderBar;
  final bool showBackButton;

  const AnalysisFeatureLayout({
    super.key,
    required this.title,
    required this.body,
    this.floatingActionButton,
    this.actions,
    this.showGenderBar = false,
    this.showBackButton = true,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, themeProvider, _) {
        return Scaffold(
          appBar: AppBar(
            title: Text(title),
            backgroundColor: Theme.of(context).colorScheme.surface,
            surfaceTintColor: Colors.transparent,
            elevation: 0,
            automaticallyImplyLeading: showBackButton,
            actions: actions,
          ),
          body: Stack(
            children: [
              // Gender decoration background
              Positioned(
                right: -50,
                top: -50,
                child: Opacity(
                  opacity: 0.08,
                  child: GenderDecoration(
                    genderExpression: themeProvider.genderExpression,
                    size: 300,
                  ),
                ),
              ),
              // Main content
              Positioned.fill(child: body),
            ],
          ),
          floatingActionButton: floatingActionButton,
          bottomNavigationBar:
              showGenderBar ? const GlobalGenderExpressionBar() : null,
        );
      },
    );
  }
}
