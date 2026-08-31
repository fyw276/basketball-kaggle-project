import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/theme/theme_model.dart';
import '../../../core/widgets/themed_page.dart';

class ProfileFormScreen extends StatefulWidget {
  const ProfileFormScreen({super.key});

  @override
  State<ProfileFormScreen> createState() => _ProfileFormScreenState();
}

class _ProfileFormScreenState extends State<ProfileFormScreen> {
  final _formKey = GlobalKey<FormState>();

  ApiClient get _apiClient => context.read<AuthProvider>().apiClient;

  bool _isLoading = false;
  bool _hasExistingProfile = false;

  // 表单字段
  final _heightController = TextEditingController();

  String? _bodyType;
  String? _skinTone;
  String? _budgetRange;
  final List<String> _stylePreference = [];
  final List<String> _avoidBodyParts = [];

  // 选项数据（匹配后端要求）
  final List<String> _bodyTypeOptions = ['偏瘦', '微胖', '梨形', '倒三角', '沙漏', '矩形'];
  final List<String> _skinToneOptions = ['冷白', '黄皮', '小麦', '深色'];
  final List<String> _budgetRangeOptions = ['经济', '中等', '高端'];
  final List<String> _styleOptions = [
    '通勤',
    '学院',
    '甜酷',
    '简约',
    '街头',
    '复古',
    '休闲',
    '正式',
    '运动',
    '度假'
  ];
  final List<String> _bodyPartsOptions = [
    '肩',
    '腰',
    '臀',
    '大腿',
    '小腿',
    '手臂',
    '胸部'
  ];

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  @override
  void dispose() {
    _heightController.dispose();
    super.dispose();
  }

  Future<void> _loadProfile() async {
    setState(() => _isLoading = true);

    try {
      final profile = await _apiClient.getProfile();
      if (profile['error'] != null) {
        if (mounted) {
          setState(() => _hasExistingProfile = false);
        }
        return;
      }

      if (mounted) {
        setState(() {
          _hasExistingProfile = true;
          _heightController.text = profile['height']?.toString() ?? '';
          _bodyType = profile['body_type'];
          _skinTone = profile['skin_tone'];
          _budgetRange = profile['budget_range'];

          if (profile['style_preference'] != null) {
            _stylePreference.clear();
            _stylePreference
                .addAll(List<String>.from(profile['style_preference']));
          }

          if (profile['avoid_body_parts'] != null) {
            _avoidBodyParts.clear();
            _avoidBodyParts
                .addAll(List<String>.from(profile['avoid_body_parts']));
          }
        });
      }
    } catch (e) {
      // 没有画像是正常的，用户可能是第一次创建
      print('加载画像失败（可能是首次创建）: $e');
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _saveProfile() async {
    if (!_formKey.currentState!.validate()) return;

    // 验证至少选择一个风格偏好
    if (_stylePreference.isEmpty) {
      showAppSnackBar(
        context,
        '请至少选择一个风格偏好',
        backgroundColor: Colors.orange,
      );
      return;
    }

    setState(() => _isLoading = true);

    try {
      final data = {
        'height': int.parse(_heightController.text),
        'body_type': _bodyType,
        'skin_tone': _skinTone,
        'style_preference': _stylePreference,
        'budget_range': _budgetRange,
        'avoid_body_parts': _avoidBodyParts,
      };

      if (_hasExistingProfile) {
        final res = await _apiClient.updateProfile(data);
        if (res['error'] != null) {
          throw Exception(res['error'].toString());
        }
      } else {
        final res = await _apiClient.createProfile(data);
        if (res['error'] != null) {
          throw Exception(res['error'].toString());
        }
      }

      if (mounted) {
        showAppSnackBar(context, '保存成功！', backgroundColor: Colors.green);
        Navigator.pop(context);
      }
    } catch (e) {
      if (mounted) {
        showAppSnackBar(
          context,
          '保存失败：${userFacingApiError(e)}',
          backgroundColor: Colors.red,
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = StyleTokens.fromStyle(context.watch<ThemeProvider>().style);

    return ThemedPage(
      appBar: AppBar(
        title: Text(_hasExistingProfile ? '编辑用户画像' : '创建用户画像',
            style: tokens.titleStyle.copyWith(fontSize: 18)),
      ),
      child: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 说明卡片
                    Container(
                      padding: const EdgeInsets.all(12.0),
                      decoration: BoxDecoration(
                        color: tokens.surface.withValues(
                            alpha:
                                tokens.style == UserGender.male ? 0.78 : 0.70),
                        borderRadius: BorderRadius.circular(tokens.cardRadius),
                        border: Border.all(
                            color: tokens.border.withValues(alpha: 0.85)),
                        boxShadow: tokens.cardShadow(),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.info_outline, color: tokens.accent),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '完善您的个人画像，获得更精准的穿搭建议',
                              style: tokens.bodyStyle.copyWith(fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),

                    // 身高
                    TextFormField(
                      controller: _heightController,
                      decoration: const InputDecoration(
                        labelText: '身高 (cm)',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.height),
                      ),
                      keyboardType: TextInputType.number,
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return '请输入身高';
                        }
                        final height = int.tryParse(value);
                        if (height == null || height < 100 || height > 250) {
                          return '请输入有效的身高 (100-250cm)';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // 体型
                    DropdownButtonFormField<String>(
                      value: _bodyType,
                      decoration: const InputDecoration(
                        labelText: '体型',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.accessibility),
                      ),
                      items: _bodyTypeOptions.map((type) {
                        return DropdownMenuItem(
                          value: type,
                          child: Text(type),
                        );
                      }).toList(),
                      onChanged: (value) => setState(() => _bodyType = value),
                      validator: (value) => value == null ? '请选择体型' : null,
                    ),
                    const SizedBox(height: 16),

                    // 肤色
                    DropdownButtonFormField<String>(
                      value: _skinTone,
                      decoration: const InputDecoration(
                        labelText: '肤色',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.palette),
                      ),
                      items: _skinToneOptions.map((tone) {
                        return DropdownMenuItem(
                          value: tone,
                          child: Text(tone),
                        );
                      }).toList(),
                      onChanged: (value) => setState(() => _skinTone = value),
                      validator: (value) => value == null ? '请选择肤色' : null,
                    ),
                    const SizedBox(height: 16),

                    // 预算范围
                    DropdownButtonFormField<String>(
                      value: _budgetRange,
                      decoration: const InputDecoration(
                        labelText: '预算范围',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.attach_money),
                      ),
                      items: _budgetRangeOptions.map((range) {
                        return DropdownMenuItem(
                          value: range,
                          child: Text(range),
                        );
                      }).toList(),
                      onChanged: (value) =>
                          setState(() => _budgetRange = value),
                      validator: (value) => value == null ? '请选择预算范围' : null,
                    ),
                    const SizedBox(height: 24),

                    // 风格偏好
                    const Text(
                      '风格偏好（至少选择一个）',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: _styleOptions.map((style) {
                        final isSelected = _stylePreference.contains(style);
                        return FilterChip(
                          label: Text(style),
                          selected: isSelected,
                          onSelected: (selected) {
                            setState(() {
                              if (selected) {
                                _stylePreference.add(style);
                              } else {
                                _stylePreference.remove(style);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 24),

                    // 避免强调的身体部位（可选）
                    const Text(
                      '避免强调的身体部位（可选）',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: _bodyPartsOptions.map((part) {
                        final isSelected = _avoidBodyParts.contains(part);
                        return FilterChip(
                          label: Text(part),
                          selected: isSelected,
                          onSelected: (selected) {
                            setState(() {
                              if (selected) {
                                _avoidBodyParts.add(part);
                              } else {
                                _avoidBodyParts.remove(part);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 32),

                    // 保存按钮
                    ElevatedButton(
                      onPressed: _isLoading ? null : _saveProfile,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: _isLoading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text(
                              '保存',
                              style: TextStyle(fontSize: 16),
                            ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
