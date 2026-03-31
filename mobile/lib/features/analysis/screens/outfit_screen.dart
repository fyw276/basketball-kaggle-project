import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:typed_data';
import 'package:provider/provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/theme/theme_model.dart';
import '../../../core/widgets/themed_page.dart';

class OutfitScreen extends StatefulWidget {
  const OutfitScreen({super.key});

  @override
  State<OutfitScreen> createState() => _OutfitScreenState();
}

class _OutfitScreenState extends State<OutfitScreen> {
  final _apiClient = ApiClient();
  final _imagePicker = ImagePicker();

  XFile? _selectedImage;
  bool _isGenerating = false;
  Map<String, dynamic>? _recommendationResult;
  int _numOutfits = 3;

  Future<void> _pickImage() async {
    try {
      final XFile? image = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
      );

      if (image == null) return;

      setState(() {
        _selectedImage = image;
        _recommendationResult = null;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('选择图片失败: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _generateOutfits() async {
    if (_selectedImage == null) return;

    setState(() => _isGenerating = true);

    try {
      final result = await _apiClient.recommendOutfitsFromXFile(
        _selectedImage!,
        numOutfits: _numOutfits,
      );

      if (mounted) {
        setState(() => _recommendationResult = result);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('生成失败: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isGenerating = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = StyleTokens.fromStyle(context.watch<ThemeProvider>().style);

    return ThemedPage(
      appBar: AppBar(
          title: Text('穿搭推荐', style: tokens.titleStyle.copyWith(fontSize: 18))),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 说明文字
            Container(
              padding: const EdgeInsets.all(16.0),
              decoration: BoxDecoration(
                color: tokens.surface
                    .withOpacity(tokens.style == UserGender.male ? 0.78 : 0.70),
                borderRadius: BorderRadius.circular(tokens.cardRadius),
                border: Border.all(color: tokens.border.withOpacity(0.85)),
                boxShadow: tokens.cardShadow(),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.info_outline, color: tokens.accent),
                      const SizedBox(width: 8),
                      Text('功能说明',
                          style: tokens.titleStyle.copyWith(fontSize: 16)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '上传一张服饰图片，系统会根据您的衣橱和个人画像，为您推荐合适的搭配方案。',
                    style: tokens.bodyStyle,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // 推荐数量选择
            Row(
              children: [
                const Text(
                  '推荐方案数量:',
                  style: TextStyle(fontSize: 16),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Slider(
                    value: _numOutfits.toDouble(),
                    min: 1,
                    max: 5,
                    divisions: 4,
                    label: _numOutfits.toString(),
                    onChanged: (value) {
                      setState(() => _numOutfits = value.toInt());
                    },
                  ),
                ),
                Text(
                  _numOutfits.toString(),
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // 选择图片按钮
            OutlinedButton.icon(
              onPressed: _pickImage,
              icon: const Icon(Icons.image),
              label: const Text('选择服饰图片'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 16),

            // 显示选中的图片
            if (_selectedImage != null) ...[
              Card(
                clipBehavior: Clip.antiAlias,
                child: FutureBuilder<Uint8List>(
                  future: _selectedImage!.readAsBytes(),
                  builder: (context, snapshot) {
                    if (snapshot.hasData) {
                      return Image.memory(
                        snapshot.data!,
                        height: 300,
                        fit: BoxFit.cover,
                      );
                    }
                    return const SizedBox(
                      height: 300,
                      child: Center(child: CircularProgressIndicator()),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),

              // 生成按钮
              ElevatedButton(
                onPressed: _isGenerating ? null : _generateOutfits,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _isGenerating
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text(
                        '生成搭配方案',
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ],

            // 推荐结果
            if (_recommendationResult != null) ...[
              const SizedBox(height: 24),
              const Text(
                '推荐方案',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),

              // 基础服饰信息
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '基础服饰',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      _buildInfoRow('品类',
                          _recommendationResult!['base_garment']?['category']),
                      _buildInfoRow('颜色',
                          _recommendationResult!['base_garment']?['color']),
                      _buildInfoRow('风格',
                          _recommendationResult!['base_garment']?['style']),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 搭配方案列表
              if (_recommendationResult!['outfits'] != null &&
                  (_recommendationResult!['outfits'] as List).isNotEmpty) ...[
                ...(_recommendationResult!['outfits'] as List)
                    .asMap()
                    .entries
                    .map((entry) {
                  final index = entry.key;
                  final outfit = entry.value;
                  return _buildOutfitCard(index + 1, outfit);
                }).toList(),
              ] else ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Row(
                      children: [
                        Icon(Icons.info, color: Colors.orange[700]),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Text(
                            '暂时没有合适的搭配方案，请尝试添加更多服饰到衣橱。',
                            style: TextStyle(fontSize: 14),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildOutfitCard(int index, dynamic outfit) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  '方案 $index',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: _getScoreColor(outfit['score']),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '评分: ${(outfit['score'] * 100).toStringAsFixed(0)}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // 搭配服饰列表
            if (outfit['garments'] != null) ...[
              ...(outfit['garments'] as List).map((garment) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      if (garment['image_url'] != null)
                        ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image.network(
                            garment['image_url'],
                            width: 60,
                            height: 60,
                            fit: BoxFit.cover,
                          ),
                        )
                      else
                        Container(
                          width: 60,
                          height: 60,
                          decoration: BoxDecoration(
                            color: Colors.grey[300],
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Icon(Icons.checkroom),
                        ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              garment['category'] ?? '未分类',
                              style: const TextStyle(
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            Text(
                              '${garment['color'] ?? ''} · ${garment['style'] ?? ''}',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.grey[600],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ],

            // 推荐理由
            if (outfit['reason'] != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.blue[50],
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.lightbulb_outline,
                      size: 20,
                      color: Colors.blue[700],
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        outfit['reason'],
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.blue[900],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 60,
            child: Text(
              '$label:',
              style: TextStyle(
                color: Colors.grey[600],
                fontSize: 14,
              ),
            ),
          ),
          Text(
            value?.toString() ?? '未知',
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Color _getScoreColor(double? score) {
    if (score == null) return Colors.grey;
    if (score >= 0.8) return Colors.green;
    if (score >= 0.6) return Colors.orange;
    return Colors.red;
  }
}
