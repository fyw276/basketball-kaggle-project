import 'package:flutter/material.dart';
import 'auth_screen.dart';

/// 重定向到 AuthScreen（统一登录注册页）
class RegisterScreen extends StatelessWidget {
  const RegisterScreen({super.key});

  @override
  Widget build(BuildContext context) => const AuthScreen();
}
