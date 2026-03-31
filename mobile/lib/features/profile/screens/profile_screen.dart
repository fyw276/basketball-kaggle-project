import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/global_gender_expression_bar.dart';

/// User profile form screen for creating/editing user profile.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _isLoading = false;
  bool _isInitialized = false;

  String? _gender;
  double _height = 170;
  String? _bodyType;
  String? _skinTone;
  List<String> _preferredStyles = [];

  final List<String> _bodyTypes = [
    '偏瘦',
    '标准',
    '偏胖',
    '肌肉型',
    '梨形',
    '苹果型',
  ];

  final List<String> _skinTones = [
    '冷白皮',
    '自然白',
    '黄皮',
    '自然黄',
    '暖皮',
    '小麦色',
    '深肤色',
  ];

  final List<String> _allStyles = [
    '休闲',
    '商务',
    '运动',
    '甜美',
    '帅气',
    '文艺',
    '街头',
    '复古',
    '简约',
    '潮流',
  ];

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _loadProfile() async {
    final authProvider = context.read<AuthProvider>();
    try {
      final result = await authProvider.apiClient.getProfile();
      if (result != null && !result.containsKey('error')) {
        setState(() {
          _gender = result['gender']?.toString();
          _height = (result['height'] ?? 170).toDouble();
          _bodyType = result['body_type']?.toString();
          _skinTone = result['skin_tone']?.toString();
          _preferredStyles =
              List<String>.from(result['preferred_styles'] ?? []);
        });
      }
    } catch (e) {
      debugPrint('Error loading profile: $e');
    } finally {
      setState(() {
        _isInitialized = true;
      });
    }
  }

  Future<void> _saveProfile() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final authProvider = context.read<AuthProvider>();
      final data = {
        'gender': _gender,
        'height': _height,
        'body_type': _bodyType,
        'skin_tone': _skinTone,
        'preferred_styles': _preferredStyles,
      };

      final result = await authProvider.apiClient.createProfile(data);

      if (!result.containsKey('error') && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('资料保存成功')),
        );
        context.pop();
      } else {
        throw Exception(result['error'] ?? '保存失败');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('个人资料'),
        backgroundColor: Theme.of(context).colorScheme.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      body: !_isInitialized
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Gender selection
                    Text(
                      '性别',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    SegmentedButton<String>(
                      segments: const [
                        ButtonSegment(value: 'male', label: Text('男')),
                        ButtonSegment(value: 'female', label: Text('女')),
                        ButtonSegment(value: 'other', label: Text('其他')),
                      ],
                      selected: {_gender ?? ''},
                      onSelectionChanged: (values) {
                        setState(() {
                          _gender = values.first;
                        });
                      },
                    ),
                    const SizedBox(height: 24),

                    // Gender expression (for female users)
                    Consumer<ThemeProvider>(
                      builder: (context, themeProvider, _) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '性别表达指数',
                              style: Theme.of(context).textTheme.titleSmall,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              FashionPalettes.genderLabel(
                                  themeProvider.genderExpression),
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(
                                    color:
                                        Theme.of(context).colorScheme.primary,
                                  ),
                            ),
                            GlobalGenderExpressionBar(
                              value: themeProvider.genderExpression,
                              onChanged: themeProvider.setGenderExpression,
                              showLabel: false,
                            ),
                          ],
                        );
                      },
                    ),
                    const SizedBox(height: 24),

                    // Height
                    Text(
                      '身高: ${_height.toInt()} cm',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    Slider(
                      value: _height,
                      min: 140,
                      max: 200,
                      divisions: 60,
                      label: '${_height.toInt()} cm',
                      onChanged: (value) {
                        setState(() {
                          _height = value;
                        });
                      },
                    ),
                    const SizedBox(height: 24),

                    // Body type
                    Text(
                      '体型',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _bodyTypes.map((type) {
                        return ChoiceChip(
                          label: Text(type),
                          selected: _bodyType == type,
                          onSelected: (selected) {
                            setState(() {
                              _bodyType = selected ? type : null;
                            });
                          },
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 24),

                    // Skin tone
                    Text(
                      '肤色',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _skinTones.map((tone) {
                        return ChoiceChip(
                          label: Text(tone),
                          selected: _skinTone == tone,
                          onSelected: (selected) {
                            setState(() {
                              _skinTone = selected ? tone : null;
                            });
                          },
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 24),

                    // Preferred styles
                    Text(
                      '偏好风格',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: _allStyles.map((style) {
                        return FilterChip(
                          label: Text(style),
                          selected: _preferredStyles.contains(style),
                          onSelected: (selected) {
                            setState(() {
                              if (selected) {
                                _preferredStyles.add(style);
                              } else {
                                _preferredStyles.remove(style);
                              }
                            });
                          },
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 32),

                    // Save button
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _isLoading ? null : _saveProfile,
                        child: _isLoading
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Text('保存'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
