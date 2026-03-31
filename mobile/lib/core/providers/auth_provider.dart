import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/api_client.dart';

class AuthProvider extends ChangeNotifier {
  final ApiClient _apiClient;

  bool _isAuthenticated = false;
  bool _isLoading = false;
  bool _isInitialized = false;
  String? _errorMessage;
  String? _username;
  String? _token;

  AuthProvider(this._apiClient) {
    _loadToken();
  }

  bool get isAuthenticated => _isAuthenticated;
  bool get isLoading => _isLoading;
  bool get isInitialized => _isInitialized;
  String? get errorMessage => _errorMessage;
  String? get username => _username;
  String? get token => _token;
  ApiClient get apiClient => _apiClient;

  Future<void> _loadToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _token = prefs.getString('auth_token');
      _username = prefs.getString('username');
      if (_token != null && _token!.isNotEmpty) {
        _apiClient.setToken(_token!);
        _isAuthenticated = true;
      }
    } catch (e) {
      debugPrint('Error loading token: $e');
    } finally {
      _isInitialized = true;
      notifyListeners();
    }
  }

  Future<void> _saveToken(String token, String username) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('auth_token', token);
      await prefs.setString('username', username);
    } catch (e) {
      debugPrint('Error saving token: $e');
    }
  }

  Future<void> _clearToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('auth_token');
      await prefs.remove('username');
    } catch (e) {
      debugPrint('Error clearing token: $e');
    }
  }

  Future<bool> login(
      {required String username, required String password}) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final result = await _apiClient.login(username, password);

      if (result.containsKey('error')) {
        _errorMessage = result['error'].toString();
        _isLoading = false;
        notifyListeners();
        return false;
      }

      if (result.containsKey('access_token')) {
        _token = result['access_token'];
        _username = username;
        _isAuthenticated = true;
        _apiClient.setToken(_token!);
        await _saveToken(_token!, username);
        _isLoading = false;
        notifyListeners();
        return true;
      }

      // Demo mode fallback
      _isAuthenticated = true;
      _username = username;
      await _saveToken('demo_token_$username', username);
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      _errorMessage = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> register({
    required String username,
    String? email,
    required String password,
  }) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    try {
      final result = await _apiClient.register(
          username, email ?? '$username@example.com', password);

      if (result.containsKey('error')) {
        _errorMessage = result['error'].toString();
        _isLoading = false;
        notifyListeners();
        return false;
      }

      // After successful registration, log in
      return await login(username: username, password: password);
    } catch (e) {
      _errorMessage = e.toString();
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  void logout() {
    _isAuthenticated = false;
    _username = null;
    _token = null;
    _errorMessage = null;
    _apiClient.clearToken();
    _clearToken();
    notifyListeners();
  }
}
