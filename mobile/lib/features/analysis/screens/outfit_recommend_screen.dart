import 'dart:io';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/providers/auth_provider.dart';
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

  final List<String> _scenes = [
    '日常休闲',
    '职场商务',
    '约会聚会',
    '运动健身',
    '正式场合',
  ];

  Future<void> _analyze() async {
    if (_images.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请先选择图片')),
      );
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final authProvider = context.read<AuthProvider>();
      final result = await authProvider.apiClient.recommendOutfitsFromXFile(
        _images.first,
        numOutfits: 5,
        scene: _selectedScene,
      );

      setState(() {
        _result = result;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _isLoading = false;
        _result = {'error': e.toString()};
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
                });
              },
              maxImages: 1,
              hintText: '选择一张图片',
              allowMultiple: false,
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
                onSaveOutfit: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('已保存到收藏')),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}
