import 'package:flutter/material.dart';
import 'auth_screen.dart';

/// 重定向到 AuthScreen（统一登录注册页）
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) => const AuthScreen();
}
