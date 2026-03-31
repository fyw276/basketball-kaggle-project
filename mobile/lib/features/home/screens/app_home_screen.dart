import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/widgets/gender_decoration.dart';

/// App home screen with 4 feature entry cards.
class AppHomeScreen extends StatelessWidget {
  const AppHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('智能穿搭助手'),
        backgroundColor: Theme.of(context).colorScheme.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => context.push('/settings/style'),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () {
              final authProvider = context.read<AuthProvider>();
              authProvider.logout();
              context.go('/login');
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          // Background decoration
          Positioned(
            right: -80,
            bottom: 100,
            child: Opacity(
              opacity: 0.06,
              child: Consumer<ThemeProvider>(
                builder: (context, themeProvider, _) {
                  return GenderDecoration(
                    genderExpression: themeProvider.genderExpression,
                    size: 350,
                  );
                },
              ),
            ),
          ),
          // Content
          SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Welcome section
                Consumer<AuthProvider>(
                  builder: (context, authProvider, _) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '你好, ${authProvider.username ?? '用户'}',
                          style: Theme.of(context)
                              .textTheme
                              .headlineSmall
                              ?.copyWith(
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '今天想穿什么风格?',
                          style:
                              Theme.of(context).textTheme.bodyLarge?.copyWith(
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onSurfaceVariant,
                                  ),
                        ),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 24),
                // Feature grid
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 16,
                  crossAxisSpacing: 16,
                  childAspectRatio: 1.1,
                  children: [
                    _FeatureCard(
                      icon: Icons.checkroom,
                      title: '我的衣橱',
                      subtitle: '管理你的服饰',
                      color: Colors.blue,
                      onTap: () => context.push('/wardrobe'),
                    ),
                    _FeatureCard(
                      icon: Icons.style,
                      title: '穿搭推荐',
                      subtitle: '智能搭配建议',
                      color: Colors.purple,
                      onTap: () => context.push('/analysis/outfit'),
                    ),
                    _FeatureCard(
                      icon: Icons.compare,
                      title: '相似度检测',
                      subtitle: '避免重复穿搭',
                      color: Colors.orange,
                      onTap: () => context.push('/analysis/similarity'),
                    ),
                    _FeatureCard(
                      icon: Icons.grade,
                      title: '适合度分析',
                      subtitle: '评估穿搭场景',
                      color: Colors.green,
                      onTap: () => context.push('/analysis/suitability'),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                // Quick actions
                Text(
                  '快捷操作',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 12),
                _QuickActionTile(
                  icon: Icons.person_outline,
                  title: '完善个人资料',
                  subtitle: '设置体型、肤色等信息',
                  onTap: () => context.push('/profile/create'),
                ),
                _QuickActionTile(
                  icon: Icons.tune,
                  title: '风格偏好设置',
                  subtitle: '调整性别表达指数',
                  onTap: () => context.push('/settings/style'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FeatureCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const _FeatureCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: color.withOpacity(0.1),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: color.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  icon,
                  color: color,
                  size: 28,
                ),
              ),
              const Spacer(),
              Text(
                title,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: color.withOpacity(0.8),
                    ),
              ),
              const SizedBox(height: 4),
              Text(
                subtitle,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickActionTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _QuickActionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            icon,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
