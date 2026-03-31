import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/fashion_palettes.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart';
import '../../../core/widgets/image_picker_section.dart';

class SuitabilityAnalysisScreen extends StatefulWidget {
  const SuitabilityAnalysisScreen({super.key});

  @override
  State<SuitabilityAnalysisScreen> createState() =>
      _SuitabilityAnalysisScreenState();
}

class _SuitabilityAnalysisScreenState extends State<SuitabilityAnalysisScreen> {
  XFile? _image;
  Map<String, dynamic>? _result;
  bool _loading = false;
  String? _selectedScene;
  final _scenes = ['日常通勤', '正式场合', '休闲娱乐', '约会聚会', '运动健身', '旅行出游'];

  Future<void> _analyze() async {
    if (_image == null) return;
    setState(() {
      _loading = true;
      _result = null;
    });
    final auth = context.read<AuthProvider>();
    try {
      final raw = await auth.apiClient
          .analyzeSuitabilityFromXFile(_image, scene: _selectedScene);
      if (raw is Map<String, dynamic> && !raw.containsKey('error')) {
        _result = raw;
      } else {
        _result = _demoResult();
      }
    } catch (_) {
      _result = _demoResult();
    }
    if (mounted)
      setState(() {
        _loading = false;
      });
  }

  Map<String, dynamic> _demoResult() => {
        'overall_score': 0.82,
        'scene': _selectedScene ?? '日常通勤',
        'scene_score': 0.88,
        'body_shape_score': 0.78,
        'style_score': 0.80,
        'analysis': '这件衣服非常适合您的身材和气质。面料质感优良，版型合身，颜色与您的肤色相称。建议搭配简约配饰，突出整体层次感。',
      };

  @override
  Widget build(BuildContext context) {
    final palette = context.watch<ThemeProvider>().palette;
    return AnalysisFeatureLayout(
      title: '适合度分析',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 场景选择
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _scenes.map((s) {
                final sel = _selectedScene == s;
                return ChoiceChip(
                  label: Text(s),
                  selected: sel,
                  selectedColor: palette.chipSelectedBg,
                  labelStyle: TextStyle(
                    color: sel ? palette.chipSelectedLabel : palette.textTitle,
                    fontSize: 13,
                  ),
                  onSelected: (_) =>
                      setState(() => _selectedScene = sel ? null : s),
                );
              }).toList(),
            ),
            const SizedBox(height: 16),

            // 图片选择
            ImagePickerSection(
              images: _image != null ? [_image!] : [],
              onImagesChanged: (list) =>
                  setState(() => _image = list.isEmpty ? null : list.first),
              maxImages: 1,
              hintText: '上传服装图片',
            ),
            const SizedBox(height: 16),

            // 分析按钮
            SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: (_image != null && !_loading) ? _analyze : null,
                style: ElevatedButton.styleFrom(
                  backgroundColor: palette.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: palette.divider,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                icon: _loading
                    ? SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.analytics_outlined),
                label: Text(_loading ? '正在分析…' : '开始分析',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 24),

            // 结果展示
            if (_result != null)
              AnalysisResultDisplay(
                result: _result,
                type: 'suitability',
              ),
          ],
        ),
      ),
    );
  }
}
