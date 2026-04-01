import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/services/feature_local_store.dart';
import '../../../core/utils/app_snackbar.dart';
import '../../../core/widgets/analysis_feature_layout.dart';
import '../../../core/widgets/analysis_result_display.dart';
import '../../../core/widgets/image_picker_section.dart';

/// Outfit recommendation screen.
class OutfitRecommendScreen extends StatefulWidget {
  const OutfitRecommendScreen({super.key});

  @override
  State<OutfitRecommendScreen> createState() => _OutfitRecommendScreenState();
}

class _OutfitRecommendScreenState extends State<OutfitRecommendScreen> {
  final List<XFile> _images = [];
  Map<String, dynamic>? _result;
  bool _isLoading = false;
  String? _selectedScene;

  static const _cacheKey = 'outfit_recommend_v2';

  @override
  void initState() {
    super.initState();
    // 不在此恢复缓存：否则会一直显示「上一次的推荐」，换图后也容易误以为没更新。
  }

  final List<String> _scenes = [
    '日常休闲',
    '职场商务',
    '约会聚会',
    '运动健身',
    '正式场合',
  ];

  Future<void> _analyze() async {
    if (_images.isEmpty) {
      showAppSnackBar(context, '请先选择图片');
      return;
    }

    final authProvider = context.read<AuthProvider>();
    final ge = context.read<ThemeProvider>().genderExpression;

    setState(() {
      _isLoading = true;
      _result = null;
    });
    await FeatureLocalStore.clear(_cacheKey);
    if (!mounted) return;

    try {
      final result = await authProvider.apiClient.recommendOutfitsFromXFiles(
        List<dynamic>.from(_images),
        numOutfits: 5,
        genderExpression: ge,
        scene: _selectedScene,
      );

      if (result.containsKey('error')) {
        if (mounted) {
          showAppSnackBar(
            context,
            '推荐暂不可用：${userFacingApiError(result['error'])}',
          );
        }
        setState(() {
          _isLoading = false;
          _result = null;
        });
        return;
      }

      setState(() {
        _result = result;
        _isLoading = false;
      });
      FeatureLocalStore.saveJson(_cacheKey, result);
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '网络异常：${userFacingApiError(e)}');
      }
      setState(() {
        _isLoading = false;
        _result = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnalysisFeatureLayout(
      title: '穿搭推荐',
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Scene selection
            Text(
              '选择场景',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _scenes.map((scene) {
                final isSelected = _selectedScene == scene;
                return ChoiceChip(
                  label: Text(scene),
                  selected: isSelected,
                  onSelected: (selected) {
                    setState(() {
                      _selectedScene = selected ? scene : null;
                    });
                  },
                );
              }).toList(),
            ),
            const SizedBox(height: 24),
            // Image picker
            Text(
              '上传图片',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            ImagePickerSection(
              images: _images,
              onImagesChanged: (images) {
                setState(() {
                  _images.clear();
                  _images.addAll(images);
                  _result = null;
                });
                FeatureLocalStore.clear(_cacheKey);
              },
              maxImages: 5,
              hintText: '可选多张（将合并识别后一起推荐）',
              allowMultiple: true,
            ),
            const SizedBox(height: 24),
            // Analyze button
            FilledButton.icon(
              onPressed: _isLoading ? null : _analyze,
              icon: _isLoading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.auto_awesome),
              label: Text(_isLoading ? '分析中...' : '开始推荐'),
            ),
            const SizedBox(height: 24),
            // Results
            if (_result != null)
              AnalysisResultDisplay(
                result: _result,
                type: 'outfit',
                apiBaseUrl: context.read<AuthProvider>().apiClient.baseUrl,
                onSaveOutfit: () {
                  showAppSnackBar(context, '已保存到收藏');
                },
              ),
          ],
        ),
      ),
    );
  }
}
