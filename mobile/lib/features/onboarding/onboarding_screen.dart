import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../core/providers/theme_provider.dart';
import '../../core/services/feature_local_store.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _PageInfo {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String body;

  const _PageInfo({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.body,
  });
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _pageCtrl = PageController();
  int _currentPage = 0;

  static const _pages = <_PageInfo>[
    _PageInfo(
      icon: Icons.checkroom,
      iconColor: Colors.blue,
      title: '欢迎使用智能穿搭助手',
      body: '上传你的衣服照片，AI 帮你发现相似款、推荐搭配，分析适合度，还能虚拟试衣看效果。',
    ),
    _PageInfo(
      icon: Icons.auto_awesome,
      iconColor: Colors.orange,
      title: '个性化推荐更准确',
      body: '填写你的身高、体型、肤色和风格偏好后，推荐会更贴合你。完成引导后去设置里补充这些信息。',
    ),
    _PageInfo(
      icon: Icons.rocket_launch,
      iconColor: Colors.green,
      title: '准备开始！',
      body: '从「智能穿搭」开始体验，输入位置和心情，一键生成适合今天的搭配方案。',
    ),
  ];

  @override
  void dispose() {
    _pageCtrl.dispose();
    super.dispose();
  }

  void _nextPage() {
    if (_currentPage < _pages.length - 1) {
      _pageCtrl.nextPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    } else {
      _finish();
    }
  }

  void _skip() => _finish();

  Future<void> _finish() async {
    await FeatureLocalStore.markOnboardingCompleted();
    if (mounted) {
      context.go('/shell');
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;

    return Scaffold(
      backgroundColor: palette.background,
      body: SafeArea(
        child: Column(
          children: [
            Align(
              alignment: Alignment.topRight,
              child: TextButton(
                onPressed: _skip,
                child: Text(
                  '跳过',
                  style: TextStyle(color: palette.textBody, fontSize: 14),
                ),
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pageCtrl,
                onPageChanged: (i) => setState(() => _currentPage = i),
                itemCount: _pages.length,
                itemBuilder: (_, i) => _PageWidget(
                  info: _pages[i],
                  palette: palette,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 0, 32, 32),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(_pages.length, (i) {
                      final active = i == _currentPage;
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        width: active ? 24 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: active ? palette.primary : palette.divider,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 52,
                    child: FilledButton(
                      onPressed: _nextPage,
                      style: FilledButton.styleFrom(
                        backgroundColor: palette.primary,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(26),
                        ),
                      ),
                      child: Text(
                        _currentPage == _pages.length - 1 ? '开始使用' : '下一步',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
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
}

class _PageWidget extends StatelessWidget {
  final _PageInfo info;
  final dynamic palette;

  const _PageWidget({required this.info, required this.palette});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              color: info.iconColor.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(info.icon, size: 56, color: info.iconColor),
          ),
          const SizedBox(height: 40),
          Text(
            info.title,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: palette.textTitle,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            info.body,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 15,
              color: palette.textBody,
              height: 1.6,
            ),
          ),
        ],
      ),
    );
  }
}
