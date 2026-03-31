import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';

/// 登录页
/// - 渐变背景：#F9F4FB → #F6EFF7
/// - 主标语：AI 穿搭，自由表达
/// - 副标语：智能衣橱・虚拟试衣・风格自由
/// - 按钮主色：#D9A8E5 / 文字：白色
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  bool _isLogin = true;

  static const _btnColor = Color(0xFFD9A8E5);
  static const _textDark = Color(0xFF3A3A3A);

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
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFFF9F4FB), Color(0xFFF6EFF7)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(28),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 380),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Logo
                    Center(
                      child: Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          color: _btnColor.withValues(alpha: 0.2),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.checkroom,
                            size: 36, color: _btnColor),
                      ),
                    ),
                    const SizedBox(height: 20),
                    // 主标语
                    const Text(
                      'AI 穿搭，自由表达',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        color: _textDark,
                        height: 1.3,
                      ),
                    ),
                    const SizedBox(height: 8),
                    // 副标语
                    Text(
                      '智能衣橱 · 虚拟试衣 · 风格自由',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 14,
                        color: _textDark.withValues(alpha: 0.6),
                      ),
                    ),
                    const SizedBox(height: 36),
                    // Tab 切换
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.06),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: TabBar(
                        controller: _tabController,
                        indicator: BoxDecoration(
                          color: _btnColor,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        indicatorSize: TabBarIndicatorSize.tab,
                        labelColor: Colors.white,
                        unselectedLabelColor: _textDark.withValues(alpha: 0.6),
                        dividerColor: Colors.transparent,
                        tabs: const [
                          Tab(text: '登录'),
                          Tab(text: '注册'),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    // 表单
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 250),
                      child: _isLogin
                          ? const _LoginForm(key: ValueKey('login'))
                          : const _RegisterForm(key: ValueKey('register')),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ─── 登录表单 ────────────────────────────────────────────────────────

class _LoginForm extends StatefulWidget {
  const _LoginForm({super.key});
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
          _input('用户名 / 手机号', _userCtrl,
              prefix: Icons.person_outline, validator: _req),
          const SizedBox(height: 14),
          _input('密码', _pwdCtrl,
              prefix: Icons.lock_outline,
              obscure: _obscure,
              suffix: IconButton(
                icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
              validator: _req),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: () {},
              child: const Text('忘记密码？',
                  style: TextStyle(color: Color(0xFF666666), fontSize: 13)),
            ),
          ),
          const SizedBox(height: 8),
          Consumer<AuthProvider>(
            builder: (ctx, auth, _) {
              if (auth.errorMessage != null) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(auth.errorMessage!,
                      style: const TextStyle(color: Colors.red, fontSize: 13),
                      textAlign: TextAlign.center),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          _submitBtn(),
        ],
      ),
    );
  }

  Widget _submitBtn() {
    return Consumer<AuthProvider>(
      builder: (ctx, auth, _) {
        return SizedBox(
          height: 52,
          child: ElevatedButton(
            onPressed: auth.isLoading ? null : _submit,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFD9A8E5),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
              ),
            ),
            child: auth.isLoading
                ? const SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  )
                : const Text('登录',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          ),
        );
      },
    );
  }
}

// ─── 注册表单 ────────────────────────────────────────────────────────

class _RegisterForm extends StatefulWidget {
  const _RegisterForm({super.key});
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('两次密码不一致')),
      );
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
          _input('用户名', _userCtrl,
              prefix: Icons.person_outline, validator: _req),
          const SizedBox(height: 12),
          _input('邮箱', _emailCtrl,
              prefix: Icons.email_outlined, validator: _email),
          const SizedBox(height: 12),
          _input('密码', _pwdCtrl,
              prefix: Icons.lock_outline,
              obscure: _obscure,
              suffix: IconButton(
                icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
              validator: _pwd),
          const SizedBox(height: 12),
          _input('确认密码', _repCtrl,
              prefix: Icons.lock_outline,
              obscure: _obscure2,
              suffix: IconButton(
                icon: Icon(_obscure2 ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _obscure2 = !_obscure2),
              ),
              validator: _req),
          const SizedBox(height: 20),
          Consumer<AuthProvider>(
            builder: (ctx, auth, _) {
              if (auth.errorMessage != null) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Text(auth.errorMessage!,
                      style: const TextStyle(color: Colors.red, fontSize: 13),
                      textAlign: TextAlign.center),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          SizedBox(
            height: 52,
            child: ElevatedButton(
              onPressed: () =>
                  context.read<AuthProvider>().isLoading ? null : _submit(),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFD9A8E5),
                foregroundColor: Colors.white,
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: context.watch<AuthProvider>().isLoading
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('注册',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── 通用输入框 ──────────────────────────────────────────────────────

Widget _input(
  String label,
  TextEditingController ctrl, {
  IconData? prefix,
  Widget? suffix,
  bool obscure = false,
  String? Function(String?)? validator,
}) {
  return TextFormField(
    controller: ctrl,
    obscureText: obscure,
    validator: validator,
    decoration: InputDecoration(
      labelText: label,
      prefixIcon: prefix != null ? Icon(prefix) : null,
      suffixIcon: suffix,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.grey.shade300),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Color(0xFFD9A8E5), width: 1.5),
      ),
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
  );
}
