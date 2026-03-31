import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import '../../../core/services/api_client.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../core/theme/style_tokens.dart';
import '../../../core/theme/theme_model.dart';
import '../../../core/widgets/themed_page.dart';

class SimilarityScreen extends StatefulWidget {
  const SimilarityScreen({super.key});

  @override
  State<SimilarityScreen> createState() => _SimilarityScreenState();
}

class _SimilarityScreenState extends State<SimilarityScreen> {
  final _apiClient = ApiClient();
  final _imagePicker = ImagePicker();

  XFile? _selectedImage;
  bool _isAnalyzing = false;
  Map<String, dynamic>? _analysisResult;

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
        _analysisResult = null;
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

  Future<void> _analyzeSimilarity() async {
    if (_selectedImage == null) return;

    setState(() => _isAnalyzing = true);

    try {
      final result =
          await _apiClient.analyzeSimilarityFromXFile(_selectedImage!);

      if (mounted) {
        setState(() => _analysisResult = result);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('分析失败: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isAnalyzing = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = StyleTokens.fromStyle(context.watch<ThemeProvider>().style);

    return ThemedPage(
      appBar: AppBar(
          title:
              Text('相似度分析', style: tokens.titleStyle.copyWith(fontSize: 18))),
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
                    '上传一张服饰图片，系统会在您的衣橱中查找相似的服饰，帮助您避免重复购买。',
                    style: tokens.bodyStyle,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // 选择图片按钮
            OutlinedButton.icon(
              onPressed: _pickImage,
              icon: const Icon(Icons.image),
              label: const Text('选择图片'),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
            ),
            const SizedBox(height: 16),

            // 显示选中的图片
            if (_selectedImage != null) ...[
              Card(
                clipBehavior: Clip.antiAlias,
                child: FutureBuilder<List<int>>(
                  future: _selectedImage!.readAsBytes(),
                  builder: (context, snapshot) {
                    if (snapshot.hasData) {
                      return Image.memory(
                        Uint8List.fromList(snapshot.data!),
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

              // 分析按钮
              ElevatedButton(
                onPressed: _isAnalyzing ? null : _analyzeSimilarity,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: _isAnalyzing
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text(
                        '开始分析',
                        style: TextStyle(fontSize: 16),
                      ),
              ),
            ],

            // 分析结果
            if (_analysisResult != null) ...[
              const SizedBox(height: 24),
              const Text(
                '分析结果',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),

              // 识别信息
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '识别信息',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),
                      _buildInfoRow('品类',
                          _analysisResult!['target_garment']?['category']),
                      _buildInfoRow(
                          '颜色',
                          _analysisResult!['target_garment']?['main_color']
                              ?['name']),
                      if (_analysisResult!['target_garment']?['style_tags'] !=
                          null)
                        _buildInfoRow(
                            '风格',
                            (_analysisResult!['target_garment']['style_tags']
                                    as List)
                                .join(', ')),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // 相似服饰
              if (_analysisResult!['similar_garments'] != null &&
                  (_analysisResult!['similar_garments'] as List)
                      .isNotEmpty) ...[
                const Text(
                  '相似服饰',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                ...(_analysisResult!['similar_garments'] as List)
                    .map((garment) {
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: garment['image_url'] != null
                          ? Image.network(
                              garment['image_url'],
                              width: 60,
                              height: 60,
                              fit: BoxFit.cover,
                            )
                          : const Icon(Icons.checkroom, size: 40),
                      title: Text(garment['category'] ?? '未分类'),
                      subtitle: Text(
                        garment['main_color']?['name'] ?? '',
                      ),
                      trailing: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color:
                              _getSimilarityColor(garment['similarity_score']),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '${(garment['similarity_score'] * 100).toStringAsFixed(0)}%',
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ] else ...[
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Row(
                      children: [
                        Icon(Icons.check_circle, color: Colors.green[700]),
                        const SizedBox(width: 12),
                        const Expanded(
                          child: Text(
                            '没有找到相似的服饰，可以放心购买！',
                            style: TextStyle(fontSize: 14),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],

              // 推荐信息
              if (_analysisResult!['recommendation'] != null) ...[
                const SizedBox(height: 16),
                Card(
                  color: _analysisResult!['has_duplicate_warning'] == true
                      ? Colors.orange[50]
                      : Colors.green[50],
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Row(
                      children: [
                        Icon(
                          _analysisResult!['has_duplicate_warning'] == true
                              ? Icons.warning
                              : Icons.check_circle,
                          color:
                              _analysisResult!['has_duplicate_warning'] == true
                                  ? Colors.orange[700]
                                  : Colors.green[700],
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            _analysisResult!['recommendation'],
                            style: const TextStyle(fontSize: 14),
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

  Color _getSimilarityColor(double? similarity) {
    if (similarity == null) return Colors.grey;
    if (similarity >= 0.8) return Colors.red;
    if (similarity >= 0.6) return Colors.orange;
    return Colors.green;
  }
}
