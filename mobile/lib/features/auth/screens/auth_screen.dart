import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../core/providers/auth_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/widgets/chinese_fret_ring.dart';

const _kAuthTextMuted = Color(0xFF2C2C2C);

/// 登录 / 注册：主副标语固定；页面配色随全局性别表达指数；大圆角与轻阴影。
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _isLogin = true;

  static const _radiusLarge = 28.0;
  static const _radiusField = 20.0;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(() {
      setState(() => _isLogin = _tabController.index == 0);
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ThemeProvider>(
      builder: (context, tp, _) {
        final p = tp.palette;
        return Scaffold(
          backgroundColor: p.background,
          body: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(28),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 400),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(_radiusLarge),
                          child: Container(
                            width: 100,
                            height: 100,
                            color: p.primary.withValues(alpha: 0.12),
                            alignment: Alignment.center,
                            child: ChineseFretRing(
                              size: 76,
                              color: p.primary,
                              strokeWidth: 2,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 22),
                      Text(
                        'AI 穿搭，自由表达',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          color: p.textTitle,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '智能衣橱・虚拟试衣・风格自由',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 14,
                          color: p.textBody.withValues(alpha: 0.85),
                        ),
                      ),
                      const SizedBox(height: 32),
                      Container(
                        padding: const EdgeInsets.all(5),
                        decoration: BoxDecoration(
                          color: p.surface,
                          borderRadius: BorderRadius.circular(_radiusLarge),
                          boxShadow: p.cardShadows,
                          border: Border.all(color: p.divider),
                        ),
                        child: TabBar(
                          controller: _tabController,
                          indicator: BoxDecoration(
                            color: p.primary,
                            borderRadius:
                                BorderRadius.circular(_radiusLarge - 4),
                          ),
                          indicatorSize: TabBarIndicatorSize.tab,
                          labelColor: Colors.white,
                          unselectedLabelColor:
                              p.textBody.withValues(alpha: 0.55),
                          dividerColor: Colors.transparent,
                          labelStyle: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                          unselectedLabelStyle: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                          ),
                          tabs: const [
                            Tab(text: '登录'),
                            Tab(text: '注册'),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 250),
                        child: _isLogin
                            ? _LoginForm(
                                key: const ValueKey('login'),
                                mist: p.primary,
                                pageBg: p.background,
                                radiusLarge: _radiusLarge,
                                radiusField: _radiusField,
                              )
                            : _RegisterForm(
                                key: const ValueKey('register'),
                                mist: p.primary,
                                pageBg: p.background,
                                radiusLarge: _radiusLarge,
                                radiusField: _radiusField,
                              ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _LoginForm extends StatefulWidget {
  final Color mist;
  final Color pageBg;
  final double radiusLarge;
  final double radiusField;

  const _LoginForm({
    super.key,
    required this.mist,
    required this.pageBg,
    required this.radiusLarge,
    required this.radiusField,
  });

  @override
  State<_LoginForm> createState() => _LoginFormState();
}

class _LoginFormState extends State<_LoginForm> {
  final _formKey = GlobalKey<FormState>();
  final _userCtrl = TextEditingController();
  final _pwdCtrl = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _userCtrl.dispose();
    _pwdCtrl.dispose();
    super.dispose();
  }

  String? _req(String? v) => (v == null || v.trim().isEmpty) ? '不能为空' : null;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final auth = context.read<AuthProvider>();
    final ok = await auth.login(
      username: _userCtrl.text.trim(),
      password: _pwdCtrl.text,
    );
    if (ok && mounted) context.go('/shell');
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _AuthField(
            label: '用户名 / 手机号',
            ctrl: _userCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.person_outline_rounded,
            validator: _req,
          ),
          const SizedBox(height: 14),
          _AuthField(
            label: '密码',
            ctrl: _pwdCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.lock_outline_rounded,
            obscure: _obscure,
            suffix: IconButton(
              tooltip: _obscure ? '显示密码' : '隐藏密码',
              icon: Icon(
                _obscure
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                color: _kAuthTextMuted.withValues(alpha: 0.45),
              ),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
            validator: _req,
          ),
          const SizedBox(height: 6),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () {},
              child: Text(
                '忘记密码？',
                style: TextStyle(
                  color: _kAuthTextMuted.withValues(alpha: 0.45),
                  fontSize: 13,
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Consumer<AuthProvider>(
            builder: (ctx, auth, _) {
              if (auth.errorMessage != null) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    auth.errorMessage!,
                    style: const TextStyle(color: Colors.red, fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          SizedBox(
            height: 56,
            child: Consumer<AuthProvider>(
              builder: (ctx, auth, _) {
                return FilledButton(
                  onPressed: auth.isLoading ? null : _submit,
                  style: FilledButton.styleFrom(
                    backgroundColor: widget.mist,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor: widget.mist.withValues(alpha: 0.4),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(widget.radiusLarge),
                    ),
                  ),
                  child: auth.isLoading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          '登录',
                          style: TextStyle(
                              fontSize: 17, fontWeight: FontWeight.w800),
                        ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _RegisterForm extends StatefulWidget {
  final Color mist;
  final Color pageBg;
  final double radiusLarge;
  final double radiusField;

  const _RegisterForm({
    super.key,
    required this.mist,
    required this.pageBg,
    required this.radiusLarge,
    required this.radiusField,
  });

  @override
  State<_RegisterForm> createState() => _RegisterFormState();
}

class _RegisterFormState extends State<_RegisterForm> {
  final _formKey = GlobalKey<FormState>();
  final _userCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _pwdCtrl = TextEditingController();
  final _repCtrl = TextEditingController();
  bool _obscure = true;
  bool _obscure2 = true;

  @override
  void dispose() {
    _userCtrl.dispose();
    _emailCtrl.dispose();
    _pwdCtrl.dispose();
    _repCtrl.dispose();
    super.dispose();
  }

  String? _req(String? v) => (v == null || v.trim().isEmpty) ? '不能为空' : null;

  String? _email(String? v) {
    if (v == null || v.trim().isEmpty) return '不能为空';
    if (!RegExp(r'^[\w\.-]+@[\w\.-]+\.\w+$').hasMatch(v)) {
      return '邮箱格式不正确';
    }
    return null;
  }

  String? _pwd(String? v) {
    if (v == null || v.isEmpty) return '不能为空';
    if (v.length < 6) return '密码至少6位';
    return null;
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_pwdCtrl.text != _repCtrl.text) {
      showAppSnackBar(context, '两次密码不一致');
      return;
    }
    final auth = context.read<AuthProvider>();
    final ok = await auth.register(
      username: _userCtrl.text.trim(),
      email: _emailCtrl.text.trim(),
      password: _pwdCtrl.text,
    );
    if (ok && mounted) context.go('/shell');
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _AuthField(
            label: '用户名',
            ctrl: _userCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.person_outline_rounded,
            validator: _req,
          ),
          const SizedBox(height: 12),
          _AuthField(
            label: '邮箱',
            ctrl: _emailCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.email_outlined,
            validator: _email,
          ),
          const SizedBox(height: 12),
          _AuthField(
            label: '密码',
            ctrl: _pwdCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.lock_outline_rounded,
            obscure: _obscure,
            suffix: IconButton(
              icon: Icon(
                _obscure
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                color: _kAuthTextMuted.withValues(alpha: 0.45),
              ),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
            validator: _pwd,
          ),
          const SizedBox(height: 12),
          _AuthField(
            label: '确认密码',
            ctrl: _repCtrl,
            mist: widget.mist,
            radius: widget.radiusField,
            prefix: Icons.lock_outline_rounded,
            obscure: _obscure2,
            suffix: IconButton(
              icon: Icon(
                _obscure2
                    ? Icons.visibility_off_outlined
                    : Icons.visibility_outlined,
                color: _kAuthTextMuted.withValues(alpha: 0.45),
              ),
              onPressed: () => setState(() => _obscure2 = !_obscure2),
            ),
            validator: _req,
          ),
          const SizedBox(height: 18),
          Consumer<AuthProvider>(
            builder: (ctx, auth, _) {
              if (auth.errorMessage != null) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(
                    auth.errorMessage!,
                    style: const TextStyle(color: Colors.red, fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          SizedBox(
            height: 56,
            child: Consumer<AuthProvider>(
              builder: (ctx, auth, _) {
                return FilledButton(
                  onPressed: auth.isLoading ? null : _submit,
                  style: FilledButton.styleFrom(
                    backgroundColor: widget.mist,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor: widget.mist.withValues(alpha: 0.4),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(widget.radiusLarge),
                    ),
                  ),
                  child: auth.isLoading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text(
                          '注册',
                          style: TextStyle(
                              fontSize: 17, fontWeight: FontWeight.w800),
                        ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _AuthField extends StatelessWidget {
  final String label;
  final TextEditingController ctrl;
  final Color mist;
  final double radius;
  final IconData prefix;
  final Widget? suffix;
  final bool obscure;
  final String? Function(String?)? validator;

  const _AuthField({
    required this.label,
    required this.ctrl,
    required this.mist,
    required this.radius,
    required this.prefix,
    this.suffix,
    this.obscure = false,
    this.validator,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: ctrl,
      obscureText: obscure,
      validator: validator,
      decoration: InputDecoration(
        hintText: label,
        hintStyle: TextStyle(color: _kAuthTextMuted.withValues(alpha: 0.7)),
        prefixIcon: Icon(prefix, color: mist.withValues(alpha: 0.85)),
        suffixIcon: suffix,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: BorderSide(color: Colors.grey.shade300),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: BorderSide(color: Colors.grey.shade300),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radius),
          borderSide: BorderSide(color: mist, width: 1.8),
        ),
        filled: true,
        fillColor: Colors.white,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      ),
    );
  }
}
